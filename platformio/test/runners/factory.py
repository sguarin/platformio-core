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

import importlib
import os
import re

from platformio.compat import load_python_module
from platformio.exception import UserSideException
from platformio.project.config import ProjectConfig
from platformio.test.result import TestSuite
from platformio.test.runners.base import TestRunnerBase, TestRunnerOptions


class TestRunnerFactory(object):
    @staticmethod
    def get_clsname(name):
        name = re.sub(r"[^\da-z\_\-]+", "", name, flags=re.I)
        return "%sTestRunner" % name.lower().capitalize()

    @classmethod
    def new(cls, test_suite, project_config, options=None) -> TestRunnerBase:
        assert isinstance(test_suite, TestSuite)
        assert isinstance(project_config, ProjectConfig)
        if options:
            assert isinstance(options, TestRunnerOptions)
        test_framework = project_config.get(
            f"env:{test_suite.env_name}", "test_framework"
        )
        module_name = f"platformio.test.runners.{test_framework}"
        runner_cls = None
        if test_framework == "custom":
            custom_runner_path = os.path.join(
                project_config.get("platformio", "test_dir"), "custom_runner.py"
            )
            try:
                mod = load_python_module(module_name, custom_runner_path)
            except ImportError:
                raise UserSideException(
                    "Could not find custom unit testing runner "
                    f"by this path -> {custom_runner_path}"
                )
        else:
            mod = importlib.import_module(module_name)
        runner_cls = getattr(mod, cls.get_clsname(test_framework))
        return runner_cls(test_suite, project_config, options)
