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

import enum
import functools
import operator
import time


class TestStatus(enum.Enum):
    PASSED = enum.auto()
    FAILED = enum.auto()
    SKIPPED = enum.auto()
    ERRORED = enum.auto()

    @classmethod
    def from_string(cls, value: str):
        value = value.lower()
        if value.startswith("pass"):
            return cls.PASSED
        if value.startswith(("ignore", "skip")):
            return cls.SKIPPED
        if value.startswith("fail"):
            return cls.FAILED
        raise ValueError(f"Unknown test status `{value}`")


class TestCaseSource:
    def __init__(self, file, line=None):
        self.file = file
        self.line = line


class TestCase:
    def __init__(  # pylint: disable=too-many-arguments
        self,
        name,
        status,
        message=None,
        stdout=None,
        source=None,
        duration=0,
        exception=None,
    ):
        assert isinstance(status, TestStatus)
        if status == TestStatus.ERRORED:
            assert isinstance(exception, Exception)
        self.name = name.strip()
        self.status = status
        self.message = message
        self.stdout = stdout
        self.source = source
        self.duration = duration
        self.exception = exception


class TestSuite:
    def __init__(self, env_name, test_name):
        self.env_name = env_name
        self.test_name = test_name
        self.timestamp = 0
        self.duration = 0
        self._cases = []
        self._finished = False

    @property
    def cases(self):
        return self._cases

    @property
    def status(self):
        for s in (TestStatus.ERRORED, TestStatus.FAILED):
            if self.get_status_nums(s):
                return s
        if self._cases and any(c.status == TestStatus.PASSED for c in self._cases):
            return TestStatus.PASSED
        return TestStatus.SKIPPED

    def get_status_nums(self, status):
        return len([True for c in self._cases if c.status == status])

    def add_case(self, case: TestCase):
        assert isinstance(case, TestCase)
        self._cases.append(case)

    def is_finished(self):
        return self._finished

    def on_start(self):
        self.timestamp = time.time()

    def on_finish(self):
        if self.is_finished():
            return
        self._finished = True
        self.duration = time.time() - self.timestamp


class TestResult:
    def __init__(self, name):
        self.name = name
        self._suites = []

    @property
    def suites(self):
        return self._suites

    def add_suite(self, suite):
        assert isinstance(suite, TestSuite)
        self._suites.append(suite)

    @property
    def duration(self):
        return functools.reduce(operator.add, [s.duration for s in self._suites])

    @property
    def case_nums(self):
        return functools.reduce(operator.add, [len(s.cases) for s in self._suites])

    @property
    def is_errored(self):
        return any(s.status == TestStatus.ERRORED for s in self._suites)

    def get_status_nums(self, status):
        return functools.reduce(
            operator.add, [s.get_status_nums(status) for s in self._suites]
        )
