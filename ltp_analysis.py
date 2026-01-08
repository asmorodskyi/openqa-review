#!/usr/bin/python3
from myutils import openQAHelper
import requests


class LTPAnalyze(openQAHelper):

    def __init__(self):
        # currently LTP mainly executed only in Incidents job group this is why we can hardcode it
        super(LTPAnalyze, self).__init__("killer", 430, 2, False, False)

    def analyze(self):
        for j1 in self.osd_get_all_jobs(
            " and test='publiccloud_ltp' and result='failed' "
        ):
            results_url = f"{self.OPENQA_URL_BASE}tests/{j1.id}/file/results.json"
            code = requests.head(results_url)
            if code.status_code == 200:
                result = self.request_get(results_url)
                failed_modules = []
                for mod1 in result["results"]:
                    if mod1["status"] == "fail":
                        failed_modules.append(mod1["test_fqn"])
                self.logger.info(j1.investigate_str(failed_modules))


def main():

    LTPAnalyze().analyze()


if __name__ == "__main__":
    main()
