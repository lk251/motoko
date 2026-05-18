{
  description = "Motoko local terminal assistant";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";
  };

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      pkgsFor = system: import nixpkgs { inherit system; };
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        {
          default = self.packages.${system}.motoko;
          motoko = pkgs.writeShellScriptBin "motoko" ''
            exec ${pkgs.python312}/bin/python3 ${./motoko} "$@"
          '';
        }
      );

      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/motoko";
        };
      });

      checks = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        {
          syntax = pkgs.runCommand "motoko-syntax-check" { nativeBuildInputs = [ pkgs.python312 ]; } ''
            python3 -m py_compile ${./motoko}
            touch "$out"
          '';
          regression = pkgs.runCommand "motoko-regression-tests" { nativeBuildInputs = [ pkgs.python312 ]; } ''
            MOTOKO_SOURCE=${./motoko} python3 ${./tests/motoko_regression.py}
            touch "$out"
          '';
          evaluation = pkgs.runCommand "motoko-evaluation-harness" { nativeBuildInputs = [ pkgs.python312 ]; } ''
            MOTOKO_SOURCE=${./motoko} python3 ${./tests/motoko_eval.py}
            touch "$out"
          '';
        }
      );

      devShells = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        {
          default = pkgs.mkShell {
            packages = [ pkgs.python312 ];
          };
        }
      );

      formatter = forAllSystems (system: (pkgsFor system).nixfmt-rfc-style);
    };
}
