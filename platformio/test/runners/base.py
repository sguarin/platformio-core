# Copyright (c) 2014-present PlatformIO <contact@platformio.org>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import click

from platformio.exception import ReturnErrorCode
from platformio.platform.factory import PlatformFactory
from platformio.test.exception import UnitTestSuiteError
from platformio.test.result import TestCase, TestCaseSource, TestStatus
from platformio.test.runners.mixins.embedded import TestRunnerEmbeddedMixin
from platformio.test.runners.mixins.native import TestRunnerNativeMixin

CTX_META_TEST_IS_RUNNING = __name__ + ".test_running"
CTX_META_TEST_RUNNING_NAME = __name__ + ".test_running_name"


class TestRunnerOptions:  # pylint: disable=too-many-instance-attributes
    def __init__(  # pylint: disable=too-many-arguments
        self,
        verbose=False,
        without_building=False,
        without_uploading=False,
        without_testing=False,
        without_debugging=True,
        upload_port=None,
        test_port=None,
        no_reset=False,
        monitor_rts=None,
        monitor_dtr=None,
    ):
        self.verbose = verbose
        self.without_building = without_building
        self.without_uploading = without_uploading
        self.without_testing = without_testing
        self.without_debugging = without_debugging
        self.upload_port = upload_port
        self.test_port = test_port
        self.no_reset = no_reset
        self.monitor_rts = monitor_rts
        self.monitor_dtr = monitor_dtr


class TestRunnerBase(TestRunnerNativeMixin, TestRunnerEmbeddedMixin):

    NAME = None
    EXTRA_LIB_DEPS = None
    TESTCASE_PARSE_RE = None

    def __init__(self, test_suite, project_config, options=None):
        self.test_suite = test_suite
        self.options = options
        self.project_config = project_config
        self.platform = PlatformFactory.new(
            self.project_config.get(f"env:{self.test_suite.env_name}", "platform"),
            autoinstall=True,
        )
        self.cmd_ctx = None

    @property
    def name(self):
        return self.__class__.__name__.replace("TestRunner", "").lower()

    def get_test_speed(self):
        return int(
            self.project_config.get(f"env:{self.test_suite.env_name}", "test_speed")
        )

    def start(self, cmd_ctx):
        # setup command context
        self.cmd_ctx = cmd_ctx
        self.cmd_ctx.meta[CTX_META_TEST_IS_RUNNING] = True
        if self.test_suite.test_name != "*":
            self.cmd_ctx.meta[CTX_META_TEST_RUNNING_NAME] = self.test_suite.test_name

        self.test_suite.on_start()
        try:
            self.setup()
            for stage in ("building", "uploading", "testing"):
                getattr(self, f"stage_{stage}")()
        except Exception as exc:  # pylint: disable=broad-except
            click.secho(str(exc), fg="red", err=True)
            self.test_suite.add_case(
                TestCase(
                    name=f"{self.test_suite.env_name}:{self.test_suite.test_name}",
                    status=TestStatus.ERRORED,
                    exception=exc,
                )
            )
        finally:
            self.test_suite.on_finish()
            self.teardown()

    def setup(self):
        pass

    def stage_building(self):
        if self.options.without_building:
            return None
        click.secho("Building...", bold=self.options.verbose)
        targets = ["__test"]
        if not self.options.without_debugging:
            targets.append("__debug")
        if self.platform.is_embedded():
            targets.append("checkprogsize")
        try:
            return self.run_project_targets(targets)
        except ReturnErrorCode:
            raise UnitTestSuiteError("Building stage has failed, see errors above.")

    def stage_uploading(self):
        if self.options.without_uploading or not self.platform.is_embedded():
            return None
        click.secho("Uploading...", bold=self.options.verbose)
        targets = ["upload"]
        if self.options.without_building:
            targets.append("nobuild")
        else:
            targets.append("__test")
        if not self.options.without_debugging:
            targets.append("__debug")
        try:
            return self.run_project_targets(targets)
        except ReturnErrorCode:
            raise UnitTestSuiteError("Uploading stage has failed, see errors above.")

    def stage_testing(self):
        if self.options.without_testing:
            return None
        click.secho("Testing...", bold=self.options.verbose)
        if self.platform.is_embedded():
            return self.stage_testing_on_target()
        return self.stage_testing_on_host()

    def teardown(self):
        pass

    def run_project_targets(self, targets):
        # pylint: disable=import-outside-toplevel
        from platformio.commands.run.command import cli as run_cmd

        assert self.cmd_ctx
        return self.cmd_ctx.invoke(
            run_cmd,
            project_conf=self.project_config.path,
            upload_port=self.options.upload_port,
            verbose=self.options.verbose,
            silent=not self.options.verbose,
            environment=[self.test_suite.env_name],
            disable_auto_clean="nobuild" in targets,
            target=targets,
        )

    def configure_build_env(self, env):  # pylint: disable=no-self-use
        """
        Configure SCons build environment
        Called in "builder/tools/piotest" tool
        """
        return env

    def on_test_output(self, data):
        click.echo(data, nl=False)
        self.parse_testcases(data)

    def parse_testcases(self, data):
        if not self.TESTCASE_PARSE_RE:
            raise NotImplementedError()

        for line in data.split("\n"):
            line = line.strip()
            if not line:
                continue
            match = self.TESTCASE_PARSE_RE.search(line)
            if not match:
                continue
            data = match.groupdict()
            source = None
            if "source_file" in data:
                source = TestCaseSource(
                    file=data["source_file"], line=int(data.get("source_line"))
                )
            self.test_suite.add_case(
                TestCase(
                    name=data.get("name"),
                    status=TestStatus.from_string(data.get("status")),
                    message=data.get("message"),
                    stdout=line,
                    source=source,
                )
            )
