.PHONY: build run clean shell stop rebuild package

build:
	docker-compose build

run:
	docker-compose up

run-detached:
	docker-compose up -d

shell:
	docker-compose run --rm network-measurement /bin/bash

stop:
	docker-compose down

clean:
	docker-compose down -v
	rm -rf data/ results/ *.pkl

logs:
	docker-compose logs -f

rebuild:
	docker-compose build --no-cache

package:
	./package.sh