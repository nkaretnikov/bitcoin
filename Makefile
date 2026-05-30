.PHONY: clean build shell test cov

NUM_JOBS=1

# To run:
# nix-shell --pure --run 'make clean build && exec $SHELL'

shell:
	nix-shell --pure

# https://github.com/bitcoin/bitcoin/blob/master/doc/developer-notes.md#using-llvmclang-toolchain
build:
	NUM_JOBS=${NUM_JOBS} ./ci/test/04_run_coverage.sh build

test:
	NUM_JOBS=${NUM_JOBS} ./ci/test/04_run_coverage.sh test

cov:
	NUM_JOBS=${NUM_JOBS} ./ci/test/04_run_coverage.sh cov

clean:
	rm -rf build
