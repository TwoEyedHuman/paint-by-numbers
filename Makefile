SEGMENTS ?= 1000
PALETTE_K ?= 12
COMPACTNESS ?= 1.0
MIN_REGION_PX ?= 200
MIN_LABEL_PX ?= 500
DOWNSAMPLE_MAX_PX ?= 800

DC = docker compose

# Grid-search values for `make tune` (SEGMENTS × PALETTE_K)
TUNE_SEGMENTS := 1000 2000 3000 5000 8000
TUNE_K        := 10 11 12 13 15

# Grid-search values for `make tune2` (COMPACTNESS × MIN_REGION_PX), seg/k locked
TUNE_COMPACTNESS  := 0.01 0.1 1.0 5.0 10.0
TUNE_MIN_REGION   := 50 100 200 400 800
TUNE2_SEGMENTS    := 3000
TUNE2_K           := 12

.PHONY: debug build tune stitch tune2 stitch2

debug:
	$(DC) run --rm \
		-e DOWNSAMPLE_MAX_PX=$(DOWNSAMPLE_MAX_PX) \
		-e SLIC_N_SEGMENTS=$(SEGMENTS) \
		-e SLIC_COMPACTNESS=$(COMPACTNESS) \
		-e PALETTE_K=$(PALETTE_K) \
		-e MIN_REGION_PX=$(MIN_REGION_PX) \
		-e MIN_LABEL_PX=$(MIN_LABEL_PX) \
		backend python pipeline/debug.py

build:
	$(DC) build backend

tune:
	@mkdir -p tmp
	@for seg in $(TUNE_SEGMENTS); do \
		for k in $(TUNE_K); do \
			printf "\n=== seg=$$seg k=$$k ===\n"; \
			$(DC) run --rm \
				-e DOWNSAMPLE_MAX_PX=$(DOWNSAMPLE_MAX_PX) \
				-e SLIC_N_SEGMENTS=$$seg \
				-e SLIC_COMPACTNESS=$(COMPACTNESS) \
				-e PALETTE_K=$$k \
				-e MIN_REGION_PX=$(MIN_REGION_PX) \
				-e MIN_LABEL_PX=$(MIN_LABEL_PX) \
				backend python pipeline/debug.py; \
			cp backend/test_assets/output_clustered.png \
				tmp/seg$${seg}_k$${k}.png; \
		done; \
	done
	@echo "Done. 25 results in tmp/"

stitch:
	$(DC) run --rm \
		-v "$(CURDIR)/tmp:/app/tmp" \
		backend python pipeline/stitch.py \
		--tmp /app/tmp \
		--pattern 'seg(\d+)_k(\d+)\.png' \
		--row-label seg --col-label k

tune2:
	@mkdir -p tmp2
	@for comp in $(TUNE_COMPACTNESS); do \
		for minpx in $(TUNE_MIN_REGION); do \
			printf "\n=== comp=$$comp minpx=$$minpx ===\n"; \
			$(DC) run --rm \
				-e DOWNSAMPLE_MAX_PX=$(DOWNSAMPLE_MAX_PX) \
				-e SLIC_N_SEGMENTS=$(TUNE2_SEGMENTS) \
				-e SLIC_COMPACTNESS=$$comp \
				-e PALETTE_K=$(TUNE2_K) \
				-e MIN_REGION_PX=$$minpx \
				-e MIN_LABEL_PX=$(MIN_LABEL_PX) \
				backend python pipeline/debug.py; \
			cp backend/test_assets/output_clustered.png \
				tmp2/comp$${comp}_minpx$${minpx}.png; \
		done; \
	done
	@echo "Done. 25 results in tmp2/"

stitch2:
	$(DC) run --rm \
		-v "$(CURDIR)/tmp2:/app/tmp2" \
		backend python pipeline/stitch.py \
		--tmp /app/tmp2 \
		--pattern 'comp([\d.]+)_minpx(\d+)\.png' \
		--row-label comp --col-label minpx
