"""Unified command-line runner for the Intelligent Forgetting in Agentic AI project."""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def check_and_reexec_in_venv() -> None:
    """If running under a global Python interpreter and .venv exists, automatically re-execute inside .venv."""
    venv_python = Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        try:
            current_py = Path(sys.executable).resolve()
            target_py = venv_python.resolve()
            if current_py != target_py:
                cmd = [str(target_py)] + sys.argv
                res = subprocess.run(cmd)
                sys.exit(res.returncode)
        except Exception:
            pass


def set_pythonpath() -> None:
    """Ensures 'backend/src' or 'src' is in PYTHONPATH and sys.path."""
    root = Path(__file__).parent.resolve()
    backend_src = root / "backend" / "src"
    src_path = backend_src if backend_src.exists() else (root / "src")
    backend_dir = root / "backend"

    for p in [str(backend_dir), str(src_path)]:
        if p not in sys.path:
            sys.path.insert(0, p)
        if "PYTHONPATH" in os.environ:
            os.environ["PYTHONPATH"] = f"{p}{os.pathsep}{os.environ['PYTHONPATH']}"
        else:
            os.environ["PYTHONPATH"] = p


def run_api(host: str = "127.0.0.1", port: int = 8000, reload: bool = True) -> None:
    """Starts the FastAPI backend service via Uvicorn."""
    set_pythonpath()
    import uvicorn
    print(f"[*] Starting Intelligent Forgetting API on http://{host}:{port} ...")
    uvicorn.run("intelligent_forgetting.api:app", host=host, port=port, reload=reload)


def run_dashboard(port: int = 8501) -> None:
    """Launches the Streamlit interactive dashboard."""
    set_pythonpath()
    cmd = [sys.executable, "-m", "streamlit", "run", "dashboard.py", "--server.port", str(port)]
    print(f"[*] Starting Streamlit Dashboard on http://localhost:{port} ...")
    subprocess.run(cmd)


def run_tests() -> None:
    """Runs the pytest automated test suite."""
    set_pythonpath()
    test_path = "backend/tests/" if Path("backend/tests").exists() else "tests/"
    cmd = [sys.executable, "-m", "pytest", "-v", test_path]
    print(f"[*] Running pytest automated test suite in {test_path} ...")
    res = subprocess.run(cmd)
    sys.exit(res.returncode)


def run_experiment() -> None:
    """Executes the empirical benchmark comparing memory management strategies."""
    set_pythonpath()
    try:
        from experiments.run_experiment import run_benchmark
    except ImportError:
        from backend.experiments.run_experiment import run_benchmark
    print("[*] Running empirical benchmark experiment ...")
    run_benchmark()


def run_frontend(port: int = 3000) -> None:
    """Starts the Next.js / React Web Application."""
    frontend_dir = Path(__file__).parent / "frontend"
    print(f"[*] Starting Web Application on http://localhost:{port} ...")
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    subprocess.run([npm_cmd, "run", "dev", "--", "-p", str(port)], cwd=str(frontend_dir))


def init_admin(uid: str, email: str = "") -> None:
    """Provisions administrative role for a designated user UID."""
    set_pythonpath()
    from intelligent_forgetting.auth import provision_admin_user
    from intelligent_forgetting.memory_store import MemoryStore
    from intelligent_forgetting.models import UserRecord

    store = MemoryStore()
    user = store.get_user(uid)
    if not user:
        user = UserRecord(uid=uid, email=email or f"{uid}@local.admin", role="admin")
        store.upsert_user(user)
    else:
        store.update_user_role(uid, "admin", actor_uid="cli_admin_init")

    firebase_res = provision_admin_user(uid, email=email)
    print(f"[*] Initialized Admin user: UID={uid}, Email={email}")
    print(f"[*] Firebase Claims Result: {firebase_res.get('message', 'Updated')}")


def main() -> None:
    check_and_reexec_in_venv()
    parser = argparse.ArgumentParser(
        description="Intelligent Forgetting in Agentic AI: Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  py run.py api             # Start FastAPI backend on http://127.0.0.1:8000
  py run.py frontend        # Start React + TypeScript Web App on http://localhost:5173
  py run.py dashboard       # Start Streamlit dashboard on http://localhost:8501
  py run.py test            # Execute pytest suite
  py run.py experiment      # Run empirical research benchmark
  py run.py admin-init --uid admin_user_123 --email admin@example.com
        """,
    )
    parser.add_argument(
        "command",
        choices=["api", "frontend", "dashboard", "test", "tests", "experiment", "admin-init"],
        help="Subsystem to execute",
    )
    parser.add_argument("--host", default="127.0.0.1", help="API host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000 for api, 3000 for frontend, 8501 for dashboard)")
    parser.add_argument("--no-reload", action="store_true", help="Disable Uvicorn live reload")
    parser.add_argument("--uid", default="admin_user_init", help="User UID for admin-init")
    parser.add_argument("--email", default="", help="User email for admin-init")

    args = parser.parse_args()

    if args.command == "api":
        run_api(host=args.host, port=args.port, reload=not args.no_reload)
    elif args.command == "frontend":
        run_frontend(port=args.port if args.port != 8000 else 3000)
    elif args.command == "dashboard":
        run_dashboard(port=args.port if args.port != 8000 else 8501)
    elif args.command in ("test", "tests"):
        run_tests()
    elif args.command == "experiment":
        run_experiment()
    elif args.command == "admin-init":
        init_admin(uid=args.uid, email=args.email)


if __name__ == "__main__":
    main()
