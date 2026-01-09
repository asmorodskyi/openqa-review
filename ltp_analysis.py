#!/usr/bin/python3
from myutils import openQAHelper
from models import JobSQL
from collections import defaultdict
import requests


class FailedModule:
    def __init__(self) -> None:
        self.modules = defaultdict(
            lambda: {
                "arches": set(),
                "flavors": set(),
                "job_ids": set(),
                "machines": set(),
                "versions": set(),
            }
        )

    def append(self, name: str, job: JobSQL):
        m = self.modules[name]
        m["arches"].add(job.arch)
        m["flavors"].add(job.flavor)
        m["job_ids"].add(job.id)
        m["machines"].add(job.machine)
        m["versions"].add(job.version)


class LTPAnalyze(openQAHelper):

    def __init__(self):
        # currently LTP mainly executed only in Incidents job group this is why we can hardcode it
        super(LTPAnalyze, self).__init__("killer", 430, 2, False, False)

    def analyze(self):
        ranged_by_module = FailedModule()
        for j1 in self.osd_get_all_jobs(
            " and test='publiccloud_ltp' and result='failed' ", False
        ):
            results_url = f"{self.OPENQA_URL_BASE}tests/{j1.id}/file/results.json"
            code = requests.head(results_url)
            if code.status_code == 200:
                result = self.request_get(results_url)
                failed_modules = []
                for mod1 in result["results"]:
                    if mod1["status"] == "fail":
                        failed_modules.append(mod1["test_fqn"])
                        ranged_by_module.append(mod1["test_fqn"], j1)
                self.logger.info(j1.investigate_str(failed_modules))
        self.logger.info("Now ranged by LTP test view")
        for mod1 in ranged_by_module.modules.keys():
            self.logger.info(f"Module: {mod1} : {ranged_by_module.modules[mod1]}")


def main():

    LTPAnalyze().analyze()


if __name__ == "__main__":
    main()
