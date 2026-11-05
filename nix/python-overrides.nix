final: prev: {
  # These packages constrain uv_build below the version in this nixpkgs pin.
  numpy-typing-compat = prev.numpy-typing-compat.overridePythonAttrs (old: {
    postPatch = (old.postPatch or "") + ''
      substituteInPlace pyproject.toml --replace-fail 'uv_build>=0.11,<0.12' 'uv_build>=0.11'
    '';
  });
  optype = prev.optype.overridePythonAttrs (old: {
    postPatch = (old.postPatch or "") + ''
      substituteInPlace pyproject.toml --replace-fail 'uv_build>=0.11.19,<0.12.0' 'uv_build>=0.11.19'
    '';
  });
}
