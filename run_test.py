import subprocess
import time
import glob
import os

def run_examples():
    print("Running example scripts...\n")
    # Find all .py files in the examples folder.
    example_files = glob.glob(os.path.join("examples", "*.py"))
    for file in example_files:
        print(f"Executing {file} ...")
        # Run the example file.
        subprocess.run(["python", file], check=True)
    print("\nFinished running examples.\n")

def run_tests():
    print("Running test cases...\n")
    # Find all Python files in the tests folder that start with 'test_'
    test_files = glob.glob(os.path.join("tests", "test_*.py"))
    for file in test_files:
        print(f"Executing {file} ...")
        # Run the test file.
        subprocess.run(["python", file], check=True)
    print("\nFinished running tests.\n")

if __name__ == "__main__":
    run_examples()
    print("Waiting 20 seconds before starting tests...")
    time.sleep(20)
    run_tests()
