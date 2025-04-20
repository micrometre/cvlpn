.PHONY: run
clean:
	sudo rm public/images/*.jpg
lpdetector:
	python3 -m cvlpn.main
docs:
	sphinx-build docs _build