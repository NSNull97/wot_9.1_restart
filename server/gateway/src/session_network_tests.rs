use super::*;
fn refusal(result:Result<(),Box<dyn std::error::Error>>){
    let error=result.unwrap_err();assert_eq!(error.downcast_ref::<io::Error>().unwrap().to_string(),
        crate::identity091::game_network::UNSUPPORTED_RUNTIME);
}

#[test]
fn net02_all_eight_old_config_entrypoints_reject_lan_before_resource_capture_key_or_socket(){
    let path=crate::identity091::net02_config_tests::lan_file();let path=path.to_str().unwrap();
    // Intentionally nonexistent keys/resources never become the reported error;
    // no socket could be reached even if a regression omitted the early guard.
    refusal(serve_interactive("missing","missing",path,Some("missing")));
    for entry in[serve_arena_base_probe,serve_arena_space_probe,serve_arena_vehicle_probe,
        serve_arena_ready_probe,serve_arena_movement_probe,serve_map_drive_probe]{
        refusal(entry("missing","missing",path,"missing","missing"));
    }
    refusal(serve_map_drive("missing","missing",path,"missing",None,crate::capture091::Profile::Ordinary));
}

#[test]
fn net02_direct_common_single_runtime_cannot_bypass_the_network_capability_guard(){
    let path=crate::identity091::net02_config_tests::lan_file();let config=crate::identity091::Config::load(path.to_str().unwrap()).unwrap();
    refusal(serve_inner_drive("missing","missing",true,true,None,Some(Arc::new(config)),None,None,None));
}
