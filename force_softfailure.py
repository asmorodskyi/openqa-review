#!/usr/bin/python3

import argparse
from myutils import TaskHelper


class ForceSoftFailure(TaskHelper):

    def __init__(self, dryrun: bool = False):
        super().__init__("forceresult", dryrun)

    def run(self, jobids: list, bugid: str):
        for job in jobids:
            self.add_comment(job, comment=f"label:force_result:softfailed:{bugid}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-d",
        "--dryrun",
        action="store_true",
        help="Fake any calls to openQA with log messages",
    )
    parser.add_argument(
        "-b",
        "--bugid",
        help="Bug/Poo ID to use as execute to forcing result",
        required=True,
    )
    parser.add_argument(
        "jobids", help="space separated list of job IDs to process", nargs="+"
    )
    args = parser.parse_args()
    force = ForceSoftFailure(args.dryrun)
    force.run(args.jobids, args.bugid)


if __name__ == "__main__":
    main()
