#[test]
fn python_written_golden_is_readable() {
    let bytes = include_bytes!("../../../tests/fixtures/golden/metrics-v1.lscap");
    let mut reader = leakscope_capture::Reader::new(bytes.as_slice()).unwrap();
    assert_eq!(reader.metadata["format"], 1);
    let events: serde_json::Value =
        serde_json::from_slice(&reader.next_chunk().unwrap().unwrap()).unwrap();
    assert_eq!(events[0]["sample"]["rss"], 4096);
    assert!(reader.next_chunk().unwrap().is_none());
    assert!(!reader.recovered);
}
