{ pkgs ? import <nixpkgs> { } }:

pkgs.stdenv.mkDerivation (finalAttrs: {
  pname = "mpy-cross";
  version = "1.29.0.post2";

  src = pkgs.fetchurl {
    url = "https://files.pythonhosted.org/packages/py2.py3/m/mpy-cross/mpy_cross-${finalAttrs.version}-py2.py3-none-manylinux1_x86_64.whl";
    hash = "sha256-Am8IhwbnpLGYF+3pwiqQhuDdg31Y7CckPNC9dCs7a94=";
  };

  nativeBuildInputs = [
    pkgs.autoPatchelfHook
    pkgs.unzip
  ];

  buildInputs = [ pkgs.stdenv.cc.cc.lib ];

  unpackPhase = ''
    unzip "$src"
  '';

  installPhase = ''
    install -Dm755 \
      mpy_cross-${finalAttrs.version}.data/purelib/mpy_cross/mpy-cross \
      "$out/bin/mpy-cross"
  '';

  meta = with pkgs.lib; {
    description = "MicroPython cross compiler";
    homepage = "https://gitlab.com/alelec/mpy_cross";
    license = licenses.mit;
    platforms = [ "x86_64-linux" ];
    mainProgram = "mpy-cross";
  };
})
