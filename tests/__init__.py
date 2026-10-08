import os

# Tests never launch a browser: printing a PDF takes seconds, and the suite
# must stay under one. The printing itself is covered by `jsa doctor`.
os.environ["JSA_BROWSER"] = "none"

# Nor do they fetch the shared catalogue's hundreds of real boards. Tests that
# need a catalogue pass one explicitly.
os.environ["JSA_CATALOGUE"] = os.devnull
