.PHONY: run test docker clean

run:
	python app.py

test:
	python -m unittest discover -s tests -v

docker:
	docker compose up --build

clean:
	rm -rf __pycache__ tests/__pycache__ tests/test_runtime.db
