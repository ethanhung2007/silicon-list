import json
from pathlib import Path
from dataclasses import dataclass, field

DEFAULT_DIR = Path.home() / ".silicon-list"
SEEN_FILE = DEFAULT_DIR / "seen.json"
RESULTS_FILE = DEFAULT_DIR / "results.md"
ERRORS_FILE = DEFAULT_DIR / "errors.log"
CONFIG_FILE = DEFAULT_DIR / "config.json"

DEFAULT_SEARCH_QUERIES = [
    "FPGA intern 2026",
    "RTL design intern 2026",
    "chip design internship 2026",
    "ASIC design intern 2026",
    "firmware engineering intern 2026",
    "embedded systems intern 2026",
    "computer architecture intern 2026",
    "physical design intern 2026",
    "verification engineer intern 2026",
    "silicon engineering intern 2026",
    "silicon validation intern 2026",
    "VLSI intern 2026",
    "EDA intern 2026",
    "hardware engineering intern fall 2026",
    "FPGA intern fall 2026",
    "RTL design intern fall 2026",
    "firmware intern fall 2026",
    "embedded systems co op fall 2026",
    "hardware co op fall 2026",
    "ASIC co op fall 2026",
    "verification co op fall 2026",
    "hardware engineering intern spring 2027",
    "FPGA intern spring 2027",
    "RTL design intern spring 2027",
    "firmware intern spring 2027",
    "embedded systems co op spring 2027",
    "hardware co op spring 2027",
    "ASIC co op spring 2027",
    "verification co op spring 2027",
    "FPGA intern 2027",
    "RTL design intern 2027",
    "hardware engineering intern 2027",
    "ASIC intern summer 2027",
    "verification intern summer 2027",
    "firmware intern summer 2027",
    "digital design intern 2026",
    "digital IC design intern 2026",
    "mixed signal intern 2026",
    "analog intern 2026",
    "semiconductor intern 2026",
    "robotics firmware intern 2026",
    "electrical engineering hardware intern 2026",
    "low-level systems intern 2026",
    "signal integrity intern 2026",
    "PCB design intern 2026",
    "microcontroller firmware intern 2026",
    "new grad ASIC verification 2026",
    "new grad silicon engineer 2026",
    "new grad firmware engineer 2026",
    "FPGA intern 2026 site:jobs.lever.co",
    "FPGA intern 2026 site:boards.greenhouse.io",
    "RTL intern 2026 site:ashbyhq.com",
    "ASIC verification intern 2026 site:workdayjobs.com",
    "firmware intern 2026 site:jobs.lever.co",
    "embedded systems intern 2026 site:greenhouse.io",
    "hardware engineering co-op fall 2026 site:myworkdayjobs.com",
    "silicon engineering intern 2026 site:ashbyhq.com",
    "physical design intern 2026 site:workdayjobs.com",
    "VLSI intern 2026 site:greenhouse.io",
    "EDA intern 2026 site:jobs.lever.co",
    "design verification intern 2026 site:ashbyhq.com",
    "analog IC intern 2026 site:myworkdayjobs.com",
    "mixed signal intern 2026 site:jobs.lever.co",
    "computer architecture intern 2026 site:greenhouse.io",
]

DEFAULT_JOB_BOARD_SEARCH_QUERIES = [
    "FPGA intern 2026 site:indeed.com/viewjob",
    "ASIC verification intern 2026 site:indeed.com/viewjob",
    "firmware intern 2026 site:indeed.com/viewjob",
    "hardware engineering intern 2026 site:linkedin.com/jobs/view",
    "RTL design intern 2026 site:linkedin.com/jobs/view",
    "embedded systems intern 2026 site:linkedin.com/jobs/view",
    "silicon engineering intern 2026 site:glassdoor.com/job-listing",
    "physical design intern 2026 site:glassdoor.com/job-listing",
    "hardware co-op 2026 site:joinhandshake.com/stu/jobs",
    "firmware intern 2026 site:app.joinhandshake.com/stu/jobs",
    "ASIC intern 2026 site:simplify.jobs/p",
    "embedded intern 2026 site:simplify.jobs/p",
]

DEFAULT_SEARXNG_SEARCH_QUERIES = [
    "site:greenhouse.io fpga internship summer 2026",
    "site:jobs.lever.co asic verification intern summer 2026",
    "site:ashbyhq.com embedded firmware internship summer 2027",
    "site:workdayjobs.com rtl design co-op fall 2026",
    "site:myworkdayjobs.com hardware engineering intern silicon",
    "site:smartrecruiters.com firmware intern embedded systems 2026",
    "site:icims.com fpga intern verilog 2026",
    "site:oraclecloud.com silicon engineering intern summer 2026",
    "site:successfactors.com semiconductor intern 2026",
    "site:job-boards.greenhouse.io fpga intern summer 2026",
    "site:jobs.ashbyhq.com hardware intern 2026",
    "physical design intern VLSI summer 2026",
    "EDA intern design verification spring 2027",
    "hardware engineering co-op spring 2027 fpga",
    "embedded systems intern firmware fall 2026",
    "RTL design intern SystemVerilog summer 2027",
    "ASIC intern verification DV summer 2027",
    "digital design intern verilog summer 2026",
    "digital IC design intern asic summer 2026",
    "mixed signal intern analog semiconductor 2026",
    "robotics firmware intern embedded 2026",
    "electrical engineering intern hardware validation 2026",
]

DEFAULT_SEARXNG_JOB_BOARD_SEARCH_QUERIES = [
    "site:indeed.com/viewjob fpga intern 2026",
    "site:indeed.com/viewjob asic verification intern 2026",
    "site:indeed.com/viewjob firmware intern embedded 2026",
    "site:linkedin.com/jobs/view hardware engineering intern 2026",
    "site:linkedin.com/jobs/view rtl design intern 2026",
    "site:linkedin.com/jobs/view embedded systems intern 2026",
    "site:glassdoor.com/job-listing silicon engineering intern 2026",
    "site:glassdoor.com/job-listing physical design intern 2026",
    "site:joinhandshake.com/stu/jobs hardware co-op 2026",
    "site:app.joinhandshake.com/stu/jobs firmware intern 2026",
    "site:simplify.jobs/p fpga intern 2026",
    "site:simplify.jobs/p hardware engineering intern 2026",
    "site:simplify.jobs/p firmware intern 2026",
]

DEFAULT_GITHUB_SOURCE_URLS = [
    "https://api.github.com/repos/SimplifyJobs/Summer2026-Internships/contents/README.md",
    # Summer 2027 repo added by SimplifyJobs once recruiting season opens
    # "https://api.github.com/repos/SimplifyJobs/Summer2027-Internships/contents/README.md",
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md",
]

DEFAULT_GITHUB_SEARCH_QUERIES = [
    "\"fpga internship\" \"2026\"",
    "\"rtl internship\" \"2026\"",
    "\"asic internship\" \"2026\"",
    "\"digital design internship\" \"2026\"",
    "\"design verification internship\" \"2026\"",
    "\"dv internship\" \"2026\"",
    "\"physical design internship\" \"2026\"",
    "\"firmware internship\" \"2026\"",
    "\"embedded systems internship\" \"2026\"",
    "\"silicon engineering internship\" \"2026\"",
    "\"semiconductor internship\" \"2026\"",
    "\"hardware co-op\" \"2026\"",
    "\"robotics firmware internship\" \"2026\"",
    "\"fpga internship\" \"2027\"",
    "\"firmware internship\" \"2027\"",
    "\"hardware internship\" \"fall 2026\"",
    "\"hardware internship\" \"spring 2027\"",
]

DEFAULT_TARGET_KEYWORDS = [
    "FPGA", "RTL", "Verilog", "SystemVerilog", "VHDL", "firmware", "embedded", 
    "RTOS", "chip design", "ASIC", "VLSI", "physical design", "computer architecture", 
    "verification", "UVM", "DV", "EDA", "Cadence", "Synopsys", "silicon", "co-op", "coop",
    "analog", "analog ic", "mixed signal", "mixed-signal", "semiconductor", "validation",
    "test engineering", "electrical", "robotics", "low-level", "digital design",
    "signal integrity", "pcb", "microcontroller", "low latency hardware"
]

DEFAULT_PRIORITY_COMPANIES = [
    "NVIDIA", "Apple", "AMD", "Qualcomm", "Intel", "ARM", "Broadcom", "Marvell", 
    "Tenstorrent", "Cerebras", "Groq", "Rivos", "SiFive", "Google", "Meta", 
    "Microsoft", "Tesla", "Synopsys", "Cadence", "Siemens EDA", "TSMC", 
    "Applied Materials", "KLA", "Lam Research", "SpaceX", "Lockheed", 
    "Raytheon", "Northrop", "Texas Instruments", "Analog Devices", "Micron",
    "GlobalFoundries", "Samsung Semiconductor", "MediaTek", "NXP", "Infineon",
    "Renesas", "Synaptics", "Amazon", "AWS", "Blue Origin", "Boeing",
    "L3Harris", "Anduril", "Rivian"
]

DEFAULT_KNOWN_TOOLS = [
    "Verilog", "SystemVerilog", "Cadence", "Synopsys", "Vivado", "RISC-V", 
    "ARM", "RTOS", "UVM"
]

DEFAULT_TARGET_CYCLE_KEYWORDS = [
    "summer 2026",
    "fall 2026",
    "spring 2027",
    "summer 2027",
    "2026",
    "2027",
]

DEFAULT_DESCRIPTION_CATEGORIES = {
    "Firmware / Embedded": [
        "firmware", "embedded", "rtos", "microcontroller", "board bring-up", "device driver"
    ],
    "FPGA / RTL / ASIC / DV": [
        "fpga", "rtl", "asic", "verification", "design verification", "dv", "uvm",
        "verilog", "systemverilog", "vhdl", "dft"
    ],
    "Silicon / Physical Design / EDA": [
        "silicon", "physical design", "vlsi", "eda", "timing", "layout", "photonic",
        "semiconductor"
    ],
    "Hardware / Electrical": [
        "hardware", "electrical", "pcb", "analog", "validation", "test engineering",
        "instrumentation"
    ],
}

DEFAULT_HARD_EXCLUSIONS = [
    "clearance",
    "active security clearance required",
    "security clearance required",
    "must be eligible for security clearance",
    "must obtain security clearance",
    "secret clearance",
    "top secret clearance",
    "TS/SCI",
    "ITAR",
    "US person",
    "U.S. person",
    "US citizenship",
    "U.S. citizenship",
    "ITAR restricted to U.S. persons only",
    "export control restrictions apply"
]

@dataclass
class Config:
    search_queries: list[str] = field(default_factory=lambda: DEFAULT_SEARCH_QUERIES)
    target_keywords: list[str] = field(default_factory=lambda: DEFAULT_TARGET_KEYWORDS)
    priority_companies: list[str] = field(default_factory=lambda: DEFAULT_PRIORITY_COMPANIES)
    known_tools: list[str] = field(default_factory=lambda: DEFAULT_KNOWN_TOOLS)
    target_cycle_keywords: list[str] = field(default_factory=lambda: DEFAULT_TARGET_CYCLE_KEYWORDS)
    description_categories: dict[str, list[str]] = field(default_factory=lambda: DEFAULT_DESCRIPTION_CATEGORIES)
    hard_exclusions: list[str] = field(default_factory=lambda: DEFAULT_HARD_EXCLUSIONS)
    max_report_listings: int = 60
    max_listing_age_days: int = 31
    keep_unknown_posted_at: bool = True
    google_api_key_env: str = "GOOGLE_API_KEY"
    google_cse_id_env: str = "GOOGLE_CSE_ID"
    searxng_url_env: str = "SEARXNG_URL"
    searxng_url: str = "http://localhost:8080"
    search_results_per_query: int = 5
    searxng_search_queries: list[str] = field(default_factory=lambda: DEFAULT_SEARXNG_SEARCH_QUERIES)
    job_board_search_queries: list[str] = field(default_factory=lambda: DEFAULT_JOB_BOARD_SEARCH_QUERIES)
    searxng_job_board_search_queries: list[str] = field(default_factory=lambda: DEFAULT_SEARXNG_JOB_BOARD_SEARCH_QUERIES)
    github_source_urls: list[str] = field(default_factory=lambda: DEFAULT_GITHUB_SOURCE_URLS)
    github_search_queries: list[str] = field(default_factory=lambda: DEFAULT_GITHUB_SEARCH_QUERIES)
    github_search_results_per_query: int = 5
    pipeline: str = "hybrid"
    cowork_stage2: bool = True
    cowork_max_listings: int = 100
    cowork_timeout_seconds: int = 900
    hardware_bias: bool = True
    cowork_export_path: str = "~/.silicon-list/openclaw-listings.json"
    require_exact_apply_links: bool = True
    require_us_locations: bool = True
    db_enabled: bool = True
    use_new_ranker: bool = True

    def save(self, path: Path = CONFIG_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.__dict__, f, indent=4)

    @classmethod
    def load(cls, path: Path = CONFIG_FILE) -> "Config":
        if not path.exists():
            return cls()
        with open(path, 'r') as f:
            try:
                data = json.load(f)
            except Exception:
                return cls()

        # Migrate old field names and drop unknown keys so old config.json files
        # don't crash after the openclaw/hermes → cowork rename.
        _RENAMES = {
            "openclaw_stage2": "cowork_stage2",
            "openclaw_max_leads": "cowork_max_listings",
            "openclaw_export_path": "cowork_export_path",
        }
        _REMOVED = {"openclaw_search_depth", "hermes_enabled", "hermes_export_path"}

        import dataclasses
        known = {f.name for f in dataclasses.fields(cls)}
        migrated: dict = {}
        for k, v in data.items():
            if k in _REMOVED:
                continue
            migrated[_RENAMES.get(k, k)] = v

        try:
            return cls(**{k: v for k, v in migrated.items() if k in known})
        except Exception:
            return cls()
