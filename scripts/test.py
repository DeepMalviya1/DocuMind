"""
test.py

Run this from the project root:
    python scripts/test.py
"""

# import os
# import sys

# # Add project root to path so imports work
# project_root = os.path.dirname(os.path.dirname(__file__))
# sys.path.append(project_root)

# from scripts.loader import DocumentLoader


# def main():
#     # Path to docs folder
#     docs_path = os.path.join(project_root, "docs")

#     # Create loader
#     loader = DocumentLoader()

#     # Load everything in docs/
#     results = loader.load_directory(docs_path)

#     # Print results
#     for file_path, content in results.items():
#         print(f"\nFile Path:  {file_path}")
#         print(content)
#         print()

#     # Print summary
#     print(f"--- Processed {len(results)} files ---")


# if __name__ == "__main__":
#     main()


import os

from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("SECRET_KEY")
print(api_key)