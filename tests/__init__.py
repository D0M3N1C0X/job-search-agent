import os

# Tests never launch a browser: printing a PDF takes seconds, and the suite
# must stay under one. The printing itself is covered by `jsa doctor`.
os.environ["JSA_BROWSER"] = "none"
