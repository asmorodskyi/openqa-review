
class JobSQL:

    SELECT_QUERY = 'select id, test, result, state, flavor, arch, build, group_id, version from jobs where '

    def __init__(self, raw_job):
        self.id = raw_job[0]
        self.name = raw_job[1]
        self.result = raw_job[2]
        self.state = raw_job[3]
        self.flavor = raw_job[4]
        self.arch = raw_job[5]
        self.build = raw_job[6]
        self.groupid = raw_job[7]
        self.version = raw_job[8]

    def __str__(self):
        pattern = 'Job(id: {}, name: {}, result: {}, state: {}, flavor: {}, arch: {}, build: {}, groupid: {}, version: {})'
        return pattern.format(self.id, self.name, self.result, self.state, self.flavor, self.arch, self.build, self.groupid, self.version)
