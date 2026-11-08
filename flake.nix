{
  description = "ESP8266 MicroPython development environment";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  # Last hydra build before `micropython` package broke. Stuck at 1.27.0
  inputs.nixpkgs-micropython.url = "github:NixOS/nixpkgs/58528b66f0a6d8776c77167abafbccd6d0fa147c";

  outputs =
    { nixpkgs, nixpkgs-micropython, ... }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};

      micropython = nixpkgs-micropython.legacyPackages.${system}.micropython;

      python =
        (pkgs.python3.override {
          packageOverrides = import ./nix/python-overrides.nix;
        }).withPackages
          (
            p: with p; [
              matplotlib
              numpy
              pandas
              pandas-stubs
              scipy
              scipy-stubs

              schemdraw
            ]
          );
    in
    {
      nixosModules.default = import ./client/linux/module.nix;

      devShells.${system} = {
        default = pkgs.mkShell {
          packages = with pkgs; [
            python
            esptool
            mpremote
            picocom
            micropython
            (pkgs.callPackage ./nix/packages/mpy-cross { })

            mypy
            ruff
            uv

            # for ./client/linux
            libnotify

            just
          ];

          shellHook = ''
            if project_dir=$(git rev-parse --show-toplevel 2>/dev/null) &&
              grep -Fxq 'name = "RemoteIntercom"' "$project_dir/pyproject.toml" 2>/dev/null; then
              uv pip install --quiet -r "$project_dir/pyproject.toml" --extra stubs --target "$project_dir/typings"
            fi

            echo "ESP8266 MicroPython development"
          '';
        };
      };

      formatter.${system} = pkgs.nixfmt-tree;
    };
}
