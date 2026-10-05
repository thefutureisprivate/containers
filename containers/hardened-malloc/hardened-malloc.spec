Name:           obs-hardened-malloc
Version:        2026100200
Release:        0
Summary:        Shared hardened_malloc artifacts for OBS containers
License:        MIT
URL:            https://github.com/GrapheneOS/hardened_malloc
#!RemoteAsset: https://github.com/GrapheneOS/hardened_malloc/archive/refs/tags/2026100200.tar.gz sha256:494ea2ec06f6208471844de31c8a1acfe3398d2b2763d07620318c8cda61fec0
Source0:        hardened_malloc-2026100200.tar.gz
#!RemoteAsset: https://musl.libc.org/releases/musl-1.2.5.tar.gz sha256:a9a118bbe84d8764da0ea0d28b3ab3fae8477fc7e4085d90102b8596fc7c75e4
Source1:        musl-1.2.5.tar.gz
Source2:        allocator-check.c
Source3:        manifest.py
BuildRequires:  gcc
BuildRequires:  make
BuildRequires:  python3-base
ExclusiveArch:  x86_64
# Private build artifacts, not libraries for the OBS VM's own runtime.
AutoReqProv:    no

%description
One OBS build produces reusable glibc and musl allocator libraries and loading
checks. Container builds copy these artifacts; they never compile the allocator.

%prep
%setup -q -n hardened_malloc-%{version} -a 1
cp -a . ../hardened-musl

%build
mkdir -p artifacts/glibc artifacts/musl
# Avoid a libstdc++ dependency in minimal runtimes. Ordinary C++ new/delete
# still reach the interposed malloc/free; sized-delete checking is unavailable.
make %{?_smp_mflags} CONFIG_NATIVE=false CONFIG_CXX_ALLOCATOR=false
cp out/libhardened_malloc.so artifacts/glibc/
gcc -O2 -fPIE -pie -Wl,-z,relro,-z,now %{SOURCE2} -ldl -o artifacts/glibc/allocator-check
env LD_PRELOAD="$PWD/artifacts/glibc/libhardened_malloc.so" artifacts/glibc/allocator-check

# Build a musl compiler sysroot once. Its libc is NOT copied into any image.
pushd musl-1.2.5
./configure --prefix="$PWD/sysroot" --syslibdir="$PWD/sysroot/lib"
make %{?_smp_mflags}
make install
popd
musl_cc="$PWD/musl-1.2.5/sysroot/bin/musl-gcc"
make -C ../hardened-musl %{?_smp_mflags} CC="$musl_cc" CONFIG_NATIVE=false CONFIG_CXX_ALLOCATOR=false
cp ../hardened-musl/out/libhardened_malloc.so artifacts/musl/
"$musl_cc" -O2 -fPIE -pie -Wl,-z,relro,-z,now -Wl,--dynamic-linker=/lib/ld-musl-x86_64.so.1 %{SOURCE2} -ldl -o artifacts/musl/allocator-check
env LD_PRELOAD="$PWD/artifacts/musl/libhardened_malloc.so" musl-1.2.5/sysroot/lib/libc.so artifacts/musl/allocator-check
python3 %{SOURCE3} artifacts %{version} %{SOURCE0} %{SOURCE1}
cp LICENSE artifacts/LICENSE

%install
mkdir -p %{buildroot}/usr/share/obs-hardened-malloc
cp -a artifacts/. %{buildroot}/usr/share/obs-hardened-malloc/

%files
/usr/share/obs-hardened-malloc/

%changelog
* Mon Oct 05 2026 Containers maintainers <noreply@github.com> - 2026100200
- Build shared, non-native musl and glibc artifacts in OBS.
