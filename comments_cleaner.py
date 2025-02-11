#!/usr/bin/python3

import argparse
from myutils import TaskHelper


class CleanComments(TaskHelper):

    def __init__(self, dryrun: bool = False):
        super().__init__("commentscleaner", dryrun)

    def run(self, groupid: int):
        comments = self.getJobGroupComments(groupid)
        for comment in comments:
            cmd = f"openqa-cli api --host {self.OPENQA_URL_BASE} -X DELETE /groups/{groupid}/comments/{comment}"
            self.shell_exec(cmd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-d",
        "--dryrun",
        action="store_true",
        help="Fake any calls to openQA with log messages",
    )
    parser.add_argument(
        "-g",
        "--groupid",
        help="Group ID to cleanup",
        required=True,
    )
    args = parser.parse_args()
    force = CleanComments(args.dryrun)
    force.run(int(args.groupid))


if __name__ == "__main__":
    main()
