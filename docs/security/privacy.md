# Privacy

Discovery stores executable path and process name, not command-line arguments,
environment variables, request bodies, function parameters or object values.
Native snapshots aggregate type names and shallow estimates without repr or
object contents. Integration metadata accepts a fixed set of static operation
labels; callers must not encode customer IDs into those labels.

Reports redact environment paths and process keys by default. Raw capture files
contain process identity and executable paths. This distinction is visible in
documentation and must be reviewed before sharing a capture. Export redaction
for arbitrary nested raw allocation metadata is not implemented.

Data directories and credentials are private to their owner. Use encrypted
storage and an appropriate backup lifecycle when paths or symbols are sensitive.
Test browser traces may contain temporary test credentials; never run browser
trace collection against production credentials or upload production data to CI.


Native captures include pointer addresses, native symbols, loaded library paths
and available source locations. They never read object values or function
arguments. Captures and collector spools have 0600 permissions. Offline report
redaction removes path prefixes by default; symbols and addresses can still
identify software details. Review exports before sharing outside the investigation.
