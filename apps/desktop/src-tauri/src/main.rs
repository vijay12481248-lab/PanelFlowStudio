// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::{RunEvent, State};

#[derive(Clone, Default)]
struct EngineManager {
    child: Arc<Mutex<Option<Child>>>,
}

impl EngineManager {
    fn is_port_active(&self) -> bool {
        if let Ok(addr) = "127.0.0.1:8765".parse() {
            if let Ok(mut stream) = TcpStream::connect_timeout(&addr, Duration::from_millis(500)) {
                let _ = stream.set_read_timeout(Some(Duration::from_millis(600)));
                let _ = stream.set_write_timeout(Some(Duration::from_millis(600)));
                use std::io::{Read, Write};
                let req = "GET /api/system/health HTTP/1.1\r\nHost: 127.0.0.1:8765\r\nConnection: close\r\n\r\n";
                if stream.write_all(req.as_bytes()).is_ok() {
                    let mut resp = String::new();
                    if stream.read_to_string(&mut resp).is_ok() {
                        return resp.contains("PanelFlow Studio");
                    }
                }
            }
        }
        false
    }

    fn find_python_command(&self) -> (String, Vec<String>) {
        if let Ok(custom) = std::env::var("PANELFLOW_PYTHON") {
            let p = PathBuf::from(&custom);
            if p.exists() {
                return (custom, vec![]);
            }
        }

        // Test if "python" works
        let mut test_py = Command::new("python");
        test_py.arg("--version");
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            test_py.creation_flags(0x08000000);
        }
        if let Ok(out) = test_py.output() {
            if out.status.success() {
                return ("python".to_string(), vec![]);
            }
        }

        // Test if "py -3" works
        let mut test_launcher = Command::new("py");
        test_launcher.args(["-3", "--version"]);
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            test_launcher.creation_flags(0x08000000);
        }
        if let Ok(out) = test_launcher.output() {
            if out.status.success() {
                return ("py".to_string(), vec!["-3".to_string()]);
            }
        }

        // Standard Windows user/system paths
        #[cfg(windows)]
        {
            if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
                for ver in &["Python312", "Python311", "Python310"] {
                    let candidate = PathBuf::from(&local_app_data)
                        .join("Programs")
                        .join("Python")
                        .join(ver)
                        .join("python.exe");
                    if candidate.exists() {
                        return (candidate.to_string_lossy().to_string(), vec![]);
                    }
                }
            }
            for ver in &["Python312", "Python311", "Python310"] {
                let candidate = PathBuf::from(r"C:\Program Files").join(ver).join("python.exe");
                if candidate.exists() {
                    return (candidate.to_string_lossy().to_string(), vec![]);
                }
            }
        }

        ("python".to_string(), vec![])
    }

    fn find_script(&self) -> Option<PathBuf> {
        let candidates = [
            PathBuf::from("run_engine.py"),
            PathBuf::from("../../run_engine.py"),
            PathBuf::from("../run_engine.py"),
            PathBuf::from("panelflow/run_engine.py"),
            PathBuf::from("../../../run_engine.py"),
            PathBuf::from("../../../../run_engine.py"),
            PathBuf::from("resources/run_engine.py"),
        ];

        for p in &candidates {
            if p.exists() {
                if let Ok(canon) = p.canonicalize() {
                    return Some(canon);
                }
                return Some(p.clone());
            }
        }

        // Search upward from current executable
        if let Ok(exe) = std::env::current_exe() {
            let mut curr = exe.parent();
            while let Some(parent) = curr {
                let candidate = parent.join("run_engine.py");
                if candidate.exists() {
                    return candidate.canonicalize().ok().or(Some(candidate));
                }
                let nested = parent.join("panelflow").join("run_engine.py");
                if nested.exists() {
                    return nested.canonicalize().ok().or(Some(nested));
                }
                let res = parent.join("resources").join("run_engine.py");
                if res.exists() {
                    return res.canonicalize().ok().or(Some(res));
                }
                let res_nested = parent.join("resources").join("panelflow").join("run_engine.py");
                if res_nested.exists() {
                    return res_nested.canonicalize().ok().or(Some(res_nested));
                }
                curr = parent.parent();
            }
        }

        // Search upward from current working directory
        if let Ok(cwd) = std::env::current_dir() {
            let mut curr = Some(cwd.as_path());
            while let Some(parent) = curr {
                let candidate = parent.join("run_engine.py");
                if candidate.exists() {
                    return candidate.canonicalize().ok().or(Some(candidate));
                }
                let nested = parent.join("panelflow").join("run_engine.py");
                if nested.exists() {
                    return nested.canonicalize().ok().or(Some(nested));
                }
                let res = parent.join("resources").join("run_engine.py");
                if res.exists() {
                    return res.canonicalize().ok().or(Some(res));
                }
                curr = parent.parent();
            }
        }

        None
    }

    fn start_engine(&self) -> Result<String, String> {
        if self.is_port_active() {
            return Ok("Engine is already active on port 8765.".to_string());
        }

        let script = self.find_script().ok_or_else(|| {
            "Could not locate run_engine.py script in workspace or application directory.".to_string()
        })?;

        let working_dir = script.parent().unwrap_or(&script);
        let (py_cmd, py_args) = self.find_python_command();

        #[cfg(windows)]
        const CREATE_NO_WINDOW: u32 = 0x08000000;

        let mut cmd = Command::new(&py_cmd);
        for arg in py_args {
            cmd.arg(arg);
        }
        cmd.arg(&script);
        cmd.current_dir(working_dir);

        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }

        let child = cmd
            .spawn()
            .map_err(|e| format!("Failed to launch python engine ({py_cmd}): {e}"))?;

        let mut lock = self.child.lock().map_err(|e| e.to_string())?;
        *lock = Some(child);

        Ok(format!("Python engine launched successfully from {:?}", script))
    }

    fn stop_engine(&self) -> Result<String, String> {
        let mut lock = self.child.lock().map_err(|e| e.to_string())?;
        if let Some(mut child) = lock.take() {
            let pid = child.id();
            #[cfg(windows)]
            {
                use std::os::windows::process::CommandExt;
                const CREATE_NO_WINDOW: u32 = 0x08000000;
                let _ = Command::new("taskkill")
                    .args(["/F", "/T", "/PID", &pid.to_string()])
                    .creation_flags(CREATE_NO_WINDOW)
                    .output();
            }
            let _ = child.kill();
            let _ = child.wait();
            Ok(format!("Python engine (PID {}) stopped.", pid))
        } else {
            Ok("No child process owned by this shell.".to_string())
        }
    }
}

#[tauri::command]
fn start_engine_cmd(mgr: State<EngineManager>) -> Result<String, String> {
    mgr.start_engine()
}

#[tauri::command]
fn stop_engine_cmd(mgr: State<EngineManager>) -> Result<String, String> {
    mgr.stop_engine()
}

#[tauri::command]
fn restart_engine_cmd(mgr: State<EngineManager>) -> Result<String, String> {
    let _ = mgr.stop_engine();
    std::thread::sleep(Duration::from_millis(500));
    mgr.start_engine()
}

#[tauri::command]
fn get_engine_status_cmd(mgr: State<EngineManager>) -> bool {
    mgr.is_port_active()
}

fn main() {
    let engine_mgr = EngineManager::default();

    // Auto-start Python engine on application launch if not already running
    if !engine_mgr.is_port_active() {
        if let Err(e) = engine_mgr.start_engine() {
            eprintln!("[PanelFlow Tauri] Engine auto-start notice: {e}");
        }
    }

    let app = tauri::Builder::default()
        .manage(engine_mgr.clone())
        .invoke_handler(tauri::generate_handler![
            start_engine_cmd,
            stop_engine_cmd,
            restart_engine_cmd,
            get_engine_status_cmd
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(move |_app_handle, event| {
        if let RunEvent::Exit = event {
            // Clean up child process when desktop shell exits
            let _ = engine_mgr.stop_engine();
        }
    });
}
