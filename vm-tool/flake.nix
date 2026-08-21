{
  description = "Minimal QEMU runtime image";

  inputs = {
    # 2026-08-14 https://github.com/NixOS/nixpkgs/commits/nixos-26.05/
    nixpkgs.url = "github:NixOS/nixpkgs/02e08985a27c65ffd33d434eeb2e660a2e4dc84d";
  };

  outputs = { nixpkgs, ... }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        inherit system;
      };

      packages = with pkgs; [
        bashInteractive
        python3
        qemu
        virtiofsd
        passt
        iproute2
        coreutils
  findutils
  gnugrep
  gnused
  gawk
      ];
    in
    {
      packages.${system}.default =
        pkgs.dockerTools.buildLayeredImage {
          name = "qemu-runtime";
          tag = "latest";

          contents = packages;

          config = {
            Cmd = [
              "${pkgs.bashInteractive}/bin/bash"
            ];

            Env = [
              "PATH=${pkgs.lib.makeBinPath packages}"
            ];
          };
        };
    };
}
