#!/usr/bin/python3.11

import argparse
import urllib3
from myutils import TaskHelper

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class LogRegFailure(TaskHelper):

    def __init__(self):
        super(LogRegFailure, self).__init__("LogRegFailure", dryrun=False, debug=False)

    def run(self, jobid: str):
        ids = jobid.split(",")
        for one_id in ids:
            resp = self.request_get(f'{TaskHelper.OPENQA_URL_BASE}api/v1/jobs/{one_id}')
            self.logger.info(f'{resp["job"]["t_started"]} {resp["job"]["settings"]["VERSION"]} {resp["job"]["settings"]["FLAVOR"]} {resp["job"]["settings"]["ARCH"]} {resp["job"]["settings"]["PUBLIC_CLOUD_REGION"]} {TaskHelper.OPENQA_URL_BASE}t{one_id}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-j", "--jobid", required=True)
    args = parser.parse_args()

    LogRegFailure().run(args.jobid)


if __name__ == "__main__":
    main()
