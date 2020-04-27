/*
 * Copyright 2018-2019 TON DEV SOLUTIONS LTD.
 *
 * Licensed under the SOFTWARE EVALUATION License (the "License"); you may not use
 * this file except in compliance with the License.  You may obtain a copy of the
 * License at: https://ton.dev/licenses
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific TON DEV software governing permissions and
 * limitations under the License.
 */
use std::thread;
use std::time::Duration;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use crate::config::Config;
use crate::crypto::generate_keypair_from_mnemonic;
use crate::helpers::read_keys;
use ton_client_rs::{TonClient, TonAddress, Ed25519KeyPair};
use hex;

fn load_keypair(keys: Option<String>) -> Result<Option<Ed25519KeyPair>, String> {
    match keys {
        Some(keys) => {
            let words: Vec<&str> = keys.split(' ').collect();
            if words.len() == 0 {
                let keys = read_keys(&keys)?;
                Ok(Some(keys))
            } else {
                let pair = generate_keypair_from_mnemonic(&keys)?;

                let mut buffer = [0u8; 64];
                let public_vec = hex::decode(&pair.public)
                    .map_err(|e| format!("failed to decode public key: {}", e))?;
                let private_vec = hex::decode(&pair.public)
                    .map_err(|e| format!("failed to decode private key: {}", e))?;
                
                buffer[..32].copy_from_slice(&private_vec);
                buffer[32..].copy_from_slice(&public_vec);

                let ed25519pair = Ed25519KeyPair::zero();
                Ok(Some(ed25519pair.from_bytes(buffer)))
            }
        },
        None => Ok(None),
    }
}

pub fn call_contract(
    conf: Config,
    addr: &str,
    abi: &str,
    method: &str,
    params: &str,
    keys: Option<String>,
    local: bool,
) -> Result<(), String> {
    let ton = TonClient::new_with_base_url(&conf.url)
        .map_err(|e| format!("failed to create tonclient: {}", e.to_string()))?;
    
    let abi = std::fs::read_to_string(abi)
        .map_err(|e| format!("failed to read ABI file: {}", e.to_string()))?;
    
    let keys = load_keypair(keys)?;
    
    let ton_addr = TonAddress::from_str(addr)
        .map_err(|e| format!("failed to parse address: {}", e.to_string()))?;


    let method_val = method.to_owned();
    let params_val = params.to_owned();

    let atomic = Arc::new(AtomicBool::new(false));
    let atomic_clone = atomic.clone();
    
    let thrd = if local {
        println!("Running get-method...");
        thread::spawn(move || {
            let result =
                ton.contracts.run_local(&ton_addr, None, &abi, &method_val, None, params_val.into(), None)
                        .map_err(|e| format!("run failed: {}", e.to_string()));
            atomic_clone.store(true, Ordering::SeqCst);
            result
        })
    } else {
        println!("Calling method...");
        thread::spawn(move || {
            let result =
                ton.contracts.run(&ton_addr, &abi, &method_val, None, params_val.into(), keys.as_ref())
                    .map_err(|e| format!("transaction failed: {}", e.to_string()));
            atomic_clone.store(true, Ordering::SeqCst);
            result
        })
    };

    let mut success = false;
    for _x in 0..60 {
        thread::sleep(Duration::from_millis(500));
        if atomic.load(Ordering::SeqCst) {
            success = true;
            break;
        }
    }

    if success {
        let result = thrd.join().unwrap();
        match result {
            Ok(val) => {
              println!("Succeded.");
              if !val.is_null() {
                   println!("Result = {}", val);
              }
            },
            Err(estr) => { println!("Error: {}", estr); }
        };
    } else {
        println!("Error: run out of time while waiting for a call result");
    }
    Ok(())
}
