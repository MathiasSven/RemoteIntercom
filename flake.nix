{
  description = "ESP8266 MicroPython development environment";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { nixpkgs, ... }:
    let
      systems = [
        "x86_64-linux"
      ];

      forAllSystems = f:
        nixpkgs.lib.genAttrs systems
          (system: f nixpkgs.legacyPackages.${system});
    in
    {
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = with pkgs; [
            python3
            esptool
            mpremote
            picocom
            (pkgs.callPackage ./nix/packages/mpy-cross { })

            ruff
            uv

            just
          ];

          shellHook = ''
            uv pip install --quiet -r pyproject.toml --extra stubs --target typings

            echo "ESP8266 MicroPython development"
          '';
        };
      });
    };
}
