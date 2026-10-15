#![no_main]
use libfuzzer_sys::fuzz_target;
fuzz_target!(|data:&[u8]|{
    if let Ok(mut reader)=leakscope_capture::Reader::new(data){
        for _ in 0..100 {match reader.next_chunk(){Ok(Some(_))=>{},_=>break}}
    }
    use prost::Message;
    let _=leakscope_protocol::Envelope::decode(data);
});
