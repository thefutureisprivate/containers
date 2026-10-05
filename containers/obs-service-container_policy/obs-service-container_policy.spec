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
Requires:       python3-base
Requires:       podman
Requires:       build
BuildArch:      noarch

%description
Validates imported upstream digests before building containers, then audits
and smoke-tests the resulting images before OBS signs and publishes them.

%prep

%build

%install
install -d %{buildroot}/usr/lib/obs/container-policy
install -d %{buildroot}/usr/lib/obs/service
install -d %{buildroot}/usr/lib/build/post-build-checks
install -m 0644 %{SOURCE0} %{SOURCE1} %{SOURCE2} %{buildroot}/usr/lib/obs/container-policy/
install -m 0755 %{SOURCE3} %{buildroot}/usr/lib/obs/service/
install -m 0644 %{SOURCE4} %{buildroot}/usr/lib/obs/service/
install -m 0755 %{SOURCE5} %{buildroot}/usr/lib/build/post-build-checks/

%files
%dir /usr/lib/obs
%dir /usr/lib/obs/service
/usr/lib/obs/service/container_policy
/usr/lib/obs/service/container_policy.service
/usr/lib/obs/container-policy/
/usr/lib/build/post-build-checks/90-container-policy

%changelog
