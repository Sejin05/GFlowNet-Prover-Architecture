.PHONY: all build check test clippy fmt fmt-check bench audit docker-build clean

all: check test

build:
	cargo build --workspace --release

check:
	cargo check --workspace

test:
	cargo test --workspace --release

clippy:
	cargo clippy --workspace --all-targets -- -D warnings

fmt:
	cargo fmt --all

fmt-check:
	cargo fmt --all -- --check

bench:
	cargo bench -p gfn-evm

audit:
	cargo run -p gfn-cli --release -- audit --project ./tests/fixtures/multi_bug_defi_protocol

docker-build:
	docker build -t gflownet-prover:latest -f Dockerfile .

clean:
	cargo clean
