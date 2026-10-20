// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use rand::{rngs::OsRng, RngCore};
use tauri::{RunEvent, State};

fn generate_engine_token() -> String {
    let mut bytes = [0_u8; 32];
    OsRng.fill_bytes(&mut bytes);
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn engine_token_file() -> Option<PathBuf> {
    std::env::var("LOCALAPPDATA").ok().map(|root| {
        PathBuf::from(root)
            .join("PanelFlow Studio")
            .join("engine.token")
    })
}

fn loopback_engine_is_listening() -> bool {
    "127.0.0.1:8765"
        .parse()
        .ok()
        .and_then(|addr| TcpStream::connect_timeout(&addr, Duration::from_millis(250)).ok())
        .is_some()
}

#[derive(Clone)]
struct EngineManager {
    child: Arc<Mutex<Option<Child>>>,
    token: Arc<String>,
}

impl Default for EngineManager {
    fn default() -> Self {
        let token = std::env::var("PANELFLOW_ENGINE_TOKEN")
            .ok()
            .filter(|value| value.len() >= 32)
            .or_else(|| {
                if loopback_engine_is_listening() {
                    engine_token_file()
                        .and_then(|path| std::fs::read_to_string(path).ok())
                        .map(|value| value.trim().to_owned())
                        .filter(|value| value.len() >= 32)
                } else {
                    None
                }
            })
            .unwrap_or_else(generate_engine_token);
        if let Some(path) = engine_token_file() {
            if let Some(parent) = path.parent() {
                let _ = std::fs::create_dir_all(parent);
            }
            let _ = std::fs::write(path, token.as_bytes());
        }
        Self {
            child: Arc::new(Mutex::new(None)),
            token: Arc::new(token),
        }
    }
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

    fn find_standalone_engine(&self) -> Option<PathBuf> {
        if let Ok(custom) = std::env::var("PANELFLOW_ENGINE_BINARY") {
            let p = PathBuf::from(&custom);
            if p.exists() {
                return Some(p);
            }
        }

        let binary_names = [
            "panelflow-engine.exe",
            "panelflow-engine-x86_64-pc-windows-msvc.exe",
        ];

        let candidates = [
            PathBuf::from("engine_runtime/panelflow-engine.exe"),
            PathBuf::from("resources/engine_runtime/panelflow-engine.exe"),
            PathBuf::from("panelflow-engine.exe"),
            PathBuf::from("resources/panelflow-engine.exe"),
            PathBuf::from("binaries/panelflow-engine-x86_64-pc-windows-msvc.exe"),
            PathBuf::from("../../resources/engine_runtime/panelflow-engine.exe"),
            PathBuf::from("../resources/engine_runtime/panelflow-engine.exe"),
            PathBuf::from("release/engine_runtime/panelflow-engine.exe"),
            PathBuf::from("../release/engine_runtime/panelflow-engine.exe"),
            PathBuf::from("../../release/engine_runtime/panelflow-engine.exe"),
            PathBuf::from("release/panelflow-engine.exe"),
            PathBuf::from("../release/panelflow-engine.exe"),
            PathBuf::from("../../release/panelflow-engine.exe"),
        ];

        for p in &candidates {
            if p.exists() {
                if let Ok(canon) = p.canonicalize() {
                    return Some(canon);
                }
                return Some(p.clone());
            }
        }

        if let Ok(exe) = std::env::current_exe() {
            let mut curr = exe.parent();
            while let Some(parent) = curr {
                for name in &binary_names {
                    let checks = [
                        parent.join(name),
                        parent.join("engine_runtime").join(name),
                        parent.join("resources").join(name),
                        parent.join("resources").join("engine_runtime").join(name),
                        parent.join("binaries").join(name),
                        parent.join("release").join(name),
                        parent.join("release").join("engine_runtime").join(name),
                        parent.join("dist_engine").join(name),
                        parent.join("dist_engine").join("panelflow-engine").join(name),
                        parent.join("_up_").join("_up_").join("_up_").join("resources").join("engine_runtime").join(name),
                    ];
                    for candidate in &checks {
                        if candidate.exists() {
                            return candidate.canonicalize().ok().or_else(|| Some(candidate.clone()));
                        }
                    }
                }
                curr = parent.parent();
            }
        }

        if let Ok(cwd) = std::env::current_dir() {
            let mut curr = Some(cwd.as_path());
            while let Some(parent) = curr {
                for name in &binary_names {
                    let checks = [
                        parent.join(name),
                        parent.join("engine_runtime").join(name),
                        parent.join("resources").join(name),
                        parent.join("resources").join("engine_runtime").join(name),
                        parent.join("binaries").join(name),
                        parent.join("release").join(name),
                        parent.join("release").join("engine_runtime").join(name),
                        parent.join("dist_engine").join(name),
                        parent.join("dist_engine").join("panelflow-engine").join(name),
                        parent.join("_up_").join("_up_").join("_up_").join("resources").join("engine_runtime").join(name),
                    ];
                    for candidate in &checks {
                        if candidate.exists() {
                            return candidate.canonicalize().ok().or_else(|| Some(candidate.clone()));
                        }
                    }
                }
                curr = parent.parent();
            }
        }

        None
    }

    fn find_script(&self) -> Option<PathBuf> {
        if let Ok(custom) = std::env::var("PANELFLOW_ENGINE_SCRIPT") {
            let p = PathBuf::from(&custom);
            if p.exists() {
                return Some(p);
            }
        }

        let candidates = [
            PathBuf::from("run_engine.py"),
            PathBuf::from("../../run_engine.py"),
            PathBuf::from("../run_engine.py"),
            PathBuf::from("panelflow/run_engine.py"),
            PathBuf::from("../../../run_engine.py"),
            PathBuf::from("../../../../run_engine.py"),
            PathBuf::from("resources/run_engine.py"),
            PathBuf::from("_up_/_up_/_up_/run_engine.py"),
            PathBuf::from("resources/_up_/_up_/_up_/run_engine.py"),
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
                let checks = [
                    parent.join("run_engine.py"),
                    parent.join("panelflow").join("run_engine.py"),
                    parent.join("resources").join("run_engine.py"),
                    parent.join("resources").join("panelflow").join("run_engine.py"),
                    parent.join("_up_").join("_up_").join("_up_").join("run_engine.py"),
                    parent.join("resources").join("_up_").join("_up_").join("_up_").join("run_engine.py"),
                ];
                for candidate in &checks {
                    if candidate.exists() {
                        return candidate.canonicalize().ok().or_else(|| Some(candidate.clone()));
                    }
                }
                curr = parent.parent();
            }
        }

        // Search upward from current working directory
        if let Ok(cwd) = std::env::current_dir() {
            let mut curr = Some(cwd.as_path());
            while let Some(parent) = curr {
                let checks = [
                    parent.join("run_engine.py"),
                    parent.join("panelflow").join("run_engine.py"),
                    parent.join("resources").join("run_engine.py"),
                    parent.join("resources").join("panelflow").join("run_engine.py"),
                    parent.join("_up_").join("_up_").join("_up_").join("run_engine.py"),
                    parent.join("resources").join("_up_").join("_up_").join("_up_").join("run_engine.py"),
                ];
                for candidate in &checks {
                    if candidate.exists() {
                        return candidate.canonicalize().ok().or_else(|| Some(candidate.clone()));
                    }
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

        #[cfg(windows)]
        const CREATE_NO_WINDOW: u32 = 0x08000000;

        let log_path = if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
            let p = PathBuf::from(local_app_data).join("PanelFlow Studio").join("logs");
            let _ = std::fs::create_dir_all(&p);
            p.join("engine.log")
        } else {
            PathBuf::from("engine.log")
        };

        // 1. Prioritize Standalone Packaged Engine Executable (Zero External Dependencies)
        if let Some(engine_bin) = self.find_standalone_engine() {
            let working_dir = engine_bin.parent().unwrap_or(&engine_bin);
            let mut cmd = Command::new(&engine_bin);
            cmd.current_dir(working_dir);
            cmd.env("PANELFLOW_ENGINE_TOKEN", self.token.as_str());
            #[cfg(debug_assertions)]
            cmd.env("PANELFLOW_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173");

            #[cfg(windows)]
            {
                use std::os::windows::process::CommandExt;
                cmd.creation_flags(CREATE_NO_WINDOW);
            }

            if let Ok(file) = std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open(&log_path)
            {
                if let Ok(err_file) = file.try_clone() {
                    cmd.stdout(file);
                    cmd.stderr(err_file);
                }
            }

            let child = cmd
                .spawn()
                .map_err(|e| format!("Failed to launch standalone engine ({:?}): {e}", engine_bin))?;

            let mut lock = self.child.lock().map_err(|e| e.to_string())?;
            *lock = Some(child);

            // Wait up to 15 seconds for engine HTTP port to bind and become healthy
            for _ in 0..30 {
                if self.is_port_active() {
                    return Ok(format!("Standalone engine launched successfully from {:?}", engine_bin));
                }
                std::thread::sleep(Duration::from_millis(500));
            }

            return Ok(format!("Standalone engine process started from {:?}", engine_bin));
        }

        // 2. Fallback to Python Script (Development Workspace Mode)
        let script = self.find_script().ok_or_else(|| {
            "Could not locate panelflow-engine.exe or run_engine.py script in application directory.".to_string()
        })?;

        let working_dir = script.parent().unwrap_or(&script);
        let (py_cmd, py_args) = self.find_python_command();

        let mut cmd = Command::new(&py_cmd);
        for arg in py_args {
            cmd.arg(arg);
        }
        cmd.arg(&script);
        cmd.current_dir(working_dir);
        cmd.env("PANELFLOW_ENGINE_TOKEN", self.token.as_str());
        #[cfg(debug_assertions)]
        cmd.env("PANELFLOW_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173");

        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }

        if let Ok(file) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_path)
        {
            if let Ok(err_file) = file.try_clone() {
                cmd.stdout(file);
                cmd.stderr(err_file);
            }
        }

        let child = cmd
            .spawn()
            .map_err(|e| format!("Failed to launch python engine ({py_cmd}): {e}. Python 3.12+ is required when running from raw source."))?;

        let mut lock = self.child.lock().map_err(|e| e.to_string())?;
        *lock = Some(child);

        // Wait up to 10 seconds for engine HTTP port to bind and become healthy
        for _ in 0..20 {
            if self.is_port_active() {
                break;
            }
            std::thread::sleep(Duration::from_millis(500));
        }

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

#[tauri::command]
fn get_engine_token_cmd(mgr: State<EngineManager>) -> String {
    mgr.token.as_str().to_owned()
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
            get_engine_status_cmd,
            get_engine_token_cmd
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

#[cfg(test)]
mod tests {
    use super::generate_engine_token;
    use std::collections::HashSet;

    #[test]
    fn engine_tokens_are_high_entropy_and_unique() {
        let tokens: HashSet<String> = (0..100).map(|_| generate_engine_token()).collect();
        assert_eq!(tokens.len(), 100);
        assert!(tokens.iter().all(|token| token.len() >= 64));
        assert!(tokens.iter().all(|token| token.chars().all(|c| c.is_ascii_hexdigit())));
    }
}
