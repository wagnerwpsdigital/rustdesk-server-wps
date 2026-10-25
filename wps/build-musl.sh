#!/bin/bash
# Build do hbbs estático (x86_64 musl) num Mac Apple Silicon, sem docker:
# rustup + zig + cargo-zigbuild (brew install rustup zig cargo-zigbuild).
# libsodium-sys não repassa AR ao configure do libsodium; o ar do macOS
# gera um libsodium.a vazio com objetos ELF e o link falha (sodium_* undefined).
# Por isso AR/RANLIB apontam para o zig.
set -euo pipefail
export PATH="$(brew --prefix rustup)/bin:$PATH"
cd "$(dirname "$0")/.."
T=$(mktemp -d)
printf '#!/bin/sh\nexec zig ar "$@"\n' > "$T/ar"
printf '#!/bin/sh\nexec zig ranlib "$@"\n' > "$T/ranlib"
chmod +x "$T/ar" "$T/ranlib"
export AR="$T/ar" RANLIB="$T/ranlib"
rustup toolchain install stable --profile minimal
rustup target add x86_64-unknown-linux-musl --toolchain stable
cargo +stable zigbuild --release --target x86_64-unknown-linux-musl --bin hbbs
git checkout -- db_v2.sqlite3 2>/dev/null || true
file target/x86_64-unknown-linux-musl/release/hbbs
shasum -a 256 target/x86_64-unknown-linux-musl/release/hbbs
