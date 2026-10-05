Name:           obs-service-container_policy
Version:        1.0
Release:        0
Summary:        Input and runtime checks for OBS container builds
License:        MIT
URL:            https://github.com/thefutureisprivate/containers
Source0:        policy.py
Source1:        smoke.py
Source2:        images.json
Source3:        container_policy
Source4:        container_policy.service
Source5:        90-container-policy
BuildRequires:  python3-base
Requires:       python3-base
Requires:       podman
Requires:       build
Requires:       zstd
BuildArch:      noarch

%description
Validates imported upstream digests before building containers, then audits
and smoke-tests the resulting images before OBS signs and publishes them.

%package -n obs-container-policy-revision
Summary:        Rebuild dependency for the OBS container policy

%description -n obs-container-policy-revision
Content hashes of the policy source files. Container scheduling tracks this
small package so policy changes rebuild every image, without treating the
helper's build-environment dependencies as container runtime packages.

%prep

%build
sha256sum %{SOURCE0} %{SOURCE1} %{SOURCE2} %{SOURCE3} %{SOURCE4} %{SOURCE5} %{_sourcedir}/obs-service-container_policy.spec > revision.sha256

%install
install -d %{buildroot}/usr/lib/obs/container-policy
install -d %{buildroot}/usr/lib/obs/service
install -d %{buildroot}/usr/lib/build/post-build-checks
install -m 0644 %{SOURCE0} %{SOURCE1} %{SOURCE2} %{buildroot}/usr/lib/obs/container-policy/
install -m 0755 %{SOURCE3} %{buildroot}/usr/lib/obs/service/
install -m 0644 %{SOURCE4} %{buildroot}/usr/lib/obs/service/
install -m 0755 %{SOURCE5} %{buildroot}/usr/lib/build/post-build-checks/
install -D -m 0644 revision.sha256 %{buildroot}/usr/share/obs-container-policy/revision.sha256

%files
%dir /usr/lib/obs
%dir /usr/lib/obs/service
/usr/lib/obs/service/container_policy
/usr/lib/obs/service/container_policy.service
/usr/lib/obs/container-policy/
%dir /usr/lib/build/post-build-checks
/usr/lib/build/post-build-checks/90-container-policy

%files -n obs-container-policy-revision
%dir /usr/share/obs-container-policy
/usr/share/obs-container-policy/revision.sha256

%changelog
* Mon Oct 05 2026 Containers maintainers <noreply@github.com> - 1.0
- Verify native OBS registry inputs and unprivileged container runtimes.
