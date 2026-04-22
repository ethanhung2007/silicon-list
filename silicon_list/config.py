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
    "design verification intern 2026 site:ashbyhq.com"
]

DEFAULT_TARGET_KEYWORDS = [
    "FPGA", "RTL", "Verilog", "SystemVerilog", "VHDL", "firmware", "embedded", 
    "RTOS", "chip design", "ASIC", "VLSI", "physical design", "computer architecture", 
    "verification", "UVM", "DV", "EDA", "Cadence", "Synopsys", "silicon", "co-op", "coop"
]

DEFAULT_PRIORITY_COMPANIES = [
    "NVIDIA", "Apple", "AMD", "Qualcomm", "Intel", "ARM", "Broadcom", "Marvell", 
    "Tenstorrent", "Cerebras", "Groq", "Rivos", "SiFive", "Google", "Meta", 
    "Microsoft", "Tesla", "Synopsys", "Cadence", "Siemens EDA", "TSMC", 
    "Applied Materials", "KLA", "Lam Research", "SpaceX", "Lockheed", 
    "Raytheon", "Northrop"
]

DEFAULT_KNOWN_TOOLS = [
    "Verilog", "SystemVerilog", "Cadence", "Synopsys", "Vivado", "RISC-V", 
    "ARM", "RTOS", "UVM"
]

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
    hard_exclusions: list[str] = field(default_factory=lambda: DEFAULT_HARD_EXCLUSIONS)
    google_api_key_env: str = "GOOGLE_API_KEY"
    google_cse_id_env: str = "GOOGLE_CSE_ID"
    search_results_per_query: int = 5
    openclaw_export_path: str = "~/.silicon-list/openclaw-listings.json"

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
                return cls(**data)
            except Exception:
                return cls()
