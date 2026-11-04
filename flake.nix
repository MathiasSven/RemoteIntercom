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
    in
    {
      devShells.${system} = {
        default = pkgs.mkShell {
          packages = with pkgs; [
            python3
            esptool
            mpremote
            picocom
            micropython
            (pkgs.callPackage ./nix/packages/mpy-cross { })

            mypy
            ruff
            uv

            just
          ];

          shellHook = ''
            uv pip install --quiet -r pyproject.toml --extra stubs --target typings

            echo "ESP8266 MicroPython development"
          '';
        };
      };

      formatter.${system} = pkgs.nixfmt-tree;
    };
}
