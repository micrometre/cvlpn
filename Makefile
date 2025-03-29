.PHONY: run
clean:
	sudo rm public/images/*.jpg
lpdetector:
	python3 -m license_plate_detector.main
docs:
	sphinx-build docs _build