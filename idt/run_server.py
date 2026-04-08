import socket
import time
import uvicorn

_original_socketpair = socket.socketpair

def patched_socketpair(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0):
    if family not in (socket.AF_INET, socket.AF_INET6):
        return _original_socketpair(family, type, proto)

    if type != socket.SOCK_STREAM:
        raise ValueError("Only SOCK_STREAM socketpair is supported in this patch")

    host = "127.0.0.1" if family == socket.AF_INET else "::1"

    lsock = socket.socket(family, type, proto)
    try:
        lsock.bind((host, 0))
        lsock.listen(1)

        csock = socket.socket(family, type, proto)
        try:
            csock.setblocking(False)
            try:
                csock.connect(lsock.getsockname())
            except (BlockingIOError, InterruptedError):
                pass
            finally:
                csock.setblocking(True)

            ssock, _ = lsock.accept()
            return ssock, csock
        except Exception:
            csock.close()
            raise
    finally:
        lsock.close()

socket.socketpair = patched_socketpair


def open_listen_socket(host="127.0.0.1", backlog=128, max_retries=30, delay=0.3):
    last_error = None

    for attempt in range(1, max_retries + 1):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, 0))  # 랜덤 포트
            sock.listen(backlog)
            sock.setblocking(False)

            addr, port = sock.getsockname()
            print(f"[OK] listen socket opened on http://{addr}:{port} (attempt {attempt})")
            return sock, port
        except OSError as e:
            last_error = e
            print(f"[WARN] socket open failed (attempt {attempt}/{max_retries}): {e}")
            try:
                sock.close()
            except Exception:
                pass
            time.sleep(delay)

    raise last_error


if __name__ == "__main__":
    server_sock, port = open_listen_socket()

    config = uvicorn.Config(
        "src.api.main:app",
        host=None,
        port=None,
        log_level="info",
    )
    server = uvicorn.Server(config)
    server.run(sockets=[server_sock])