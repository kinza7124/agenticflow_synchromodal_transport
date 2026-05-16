try:
    from crewai_tools import BaseTool
    print("BaseTool found in crewai_tools")
except ImportError:
    print("BaseTool NOT found in crewai_tools")

try:
    from crewai.tools import BaseTool
    print("BaseTool found in crewai.tools")
except ImportError:
    print("BaseTool NOT found in crewai.tools")

import crewai
print(f"CrewAI version: {crewai.__version__}")
