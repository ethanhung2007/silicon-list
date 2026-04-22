import uuid
from typing import List
from silicon_list.models import Listing
from silicon_list.providers.base import BaseProvider

class MockProvider(BaseProvider):
    """Provides fake listings for end-to-end testing."""

    def fetch_listings(self) -> List[Listing]:
        listings = [
            Listing(
                source="mock",
                source_job_id=str(uuid.uuid4())[:8],
                company="NVIDIA",
                role="ASIC Design Engineer Intern",
                location="Santa Clara, CA",
                apply_url="https://mock.nvidia.com/apply/1",
                description="Join our team to work on next-gen GPU architectures. Strong Verilog/SystemVerilog skills needed. Active security clearance required.", # Should be excluded
                cycle="Summer 2026"
            ),
            Listing(
                source="mock",
                source_job_id=str(uuid.uuid4())[:8],
                company="Apple",
                role="Silicon Engineering Co-op",
                location="Austin, TX",
                apply_url="https://mock.apple.com/apply/2",
                description="Help design the next M-series chips. UVM and RTL experience preferred.",
                cycle="Fall 2026"
            ),
            Listing(
                source="mock",
                source_job_id=str(uuid.uuid4())[:8],
                company="Generic Startup",
                role="Senior Full Stack Engineer",
                location="San Francisco, CA",
                apply_url="https://mock.startup.com/apply/3",
                description="We need someone to build our React frontend and Node backend.", # Irrelevant + Senior
                cycle=""
            ),
            Listing(
                source="mock",
                source_job_id=str(uuid.uuid4())[:8],
                company="AMD",
                role="Firmware Intern",
                location="Remote, US",
                apply_url="https://mock.amd.com/apply/4",
                description="Write low-level C code for our new processors. C and RTOS experience required. We do not sponsor visas.", # Valid, generic sponsorship mention
                cycle="Summer 2026"
            ),
            Listing(
                source="mock",
                source_job_id=str(uuid.uuid4())[:8],
                company="Intel",
                role="Hardware Verification Intern",
                location="Hillsboro, OR",
                apply_url="https://mock.intel.com/apply/5",
                description="Verify complex logic blocks using Synopsys tools and SystemVerilog.",
                cycle="Spring 2027"
            ),
            Listing(
                source="mock",
                source_job_id=str(uuid.uuid4())[:8],
                company="SpaceX",
                role="Avionics Embedded Software Co-op",
                location="Hawthorne, CA",
                apply_url="https://mock.spacex.com/apply/6",
                description="Write software for Starship. Must be a US person due to ITAR restrictions.", # Should be excluded
                cycle="Fall 2026"
            ),
        ]
        
        return listings
