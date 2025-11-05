#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

ENVIRONMENT = os.environ.get("ENVIRONMENT", "environment")
TEST_ENVIRONMENT = os.environ.get("TEST_ENVIRONMENT", "test")
DEVELOPMENT_ENVIRONMENT = os.environ.get("DEVELOPMENT_ENVIRONMENT", "develop")
PRODUCTION_ENVIRONMENT = os.environ.get("PRODUCTION_ENVIRONMENT", "product")

VERSION = os.environ.get("VERSION", "version")
GROUP = os.environ.get("GROUP", "group")

TRANSPORT = os.environ.get("TRANSPORT", "transport")
AIO_TRANSPORT = os.environ.get("AIO_TRANSPORT", "aio")