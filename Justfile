set unstable

build:
    find src/lib/ -name '*.py' -exec just compile {} \;
    cp -f src/main.py dist/
    cp -rf src/www dist/

copy: build
    mpremote cp dist/main.py :
    mpremote cp -r dist/lib :
    mpremote cp -r dist/www :

[arg("clear-cred", long="clear-cred", short="c", value="true")]
reset clear-cred="false":
    {{ if clear-cred == "true" { "mpremote rm intercom-config.json" } else { ":" } }}
    mpremote reset

[cache(inputs=file, outputs=replace(replace(file, "src/", "dist/"), ".py", ".mpy"))]
[private]
[script]
compile file:
    mkdir -p "$(dirname '{{ replace(file, "src/", "dist/") }}')"
    mpy-cross -o '{{ replace(replace(file, "src/", "dist/"), ".py", ".mpy") }}' '{{ file }}'

clean:
    rm -rf ./dist

format:
    just --format
    nix fmt
    ruff format

check:
    mypy
    ruff check

sim-test heap="52K":
    python tests/simulate.py test --heap {{ heap }}

sim heap="52K":
    python tests/simulate.py serve --heap {{ heap }}
