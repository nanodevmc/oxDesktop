/// Utility functions for version comparison and downgrade detection in oxDesktop installers.

/// Extracts numeric version components from a version string.
/// Handles prefixes like 'v', 'V', 'oxDesktop ', and strips pre-release suffixes
/// such as '-beta', '-dev', '-preview', ' (beta)', etc.
pub fn parse_version_numbers(v: &str) -> Vec<u64> {
    let s = v.trim();
    let s = s.strip_prefix("oxDesktop").unwrap_or(s).trim();
    let s = s.strip_prefix('v').or_else(|| s.strip_prefix('V')).unwrap_or(s).trim();

    // Take only the part before pre-release separators (-, _, space, opening parenthesis)
    let main_part = s
        .split(|c: char| c == '-' || c == '_' || c == ' ' || c == '(')
        .next()
        .unwrap_or("");

    main_part
        .split('.')
        .filter_map(|part| part.trim().parse::<u64>().ok())
        .collect()
}

/// Checks whether the version string contains any pre-release or development markers.
pub fn has_prerelease_marker(v: &str) -> bool {
    let lower = v.to_lowercase();
    lower.contains("beta")
        || lower.contains("dev")
        || lower.contains("alpha")
        || lower.contains("preview")
        || lower.contains("rc")
}

/// Returns true if version `v1` is strictly greater than version `v2` numerically.
pub fn is_version_greater(v1: &str, v2: &str) -> bool {
    let nums1 = parse_version_numbers(v1);
    let nums2 = parse_version_numbers(v2);

    let max_len = std::cmp::max(nums1.len(), nums2.len());
    for i in 0..max_len {
        let n1 = nums1.get(i).copied().unwrap_or(0);
        let n2 = nums2.get(i).copied().unwrap_or(0);
        if n1 > n2 {
            return true;
        } else if n1 < n2 {
            return false;
        }
    }
    false
}

/// Determines whether installing `target` over `installed` constitutes a downgrade or replacement of a preview/beta version.
/// This is true if:
/// 1. `installed` is numerically strictly newer than `target` (e.g. installed 7.4.7 or 7.5.0 vs current 7.4.6).
/// 2. `installed` has a pre-release marker (beta, dev, alpha, preview, rc) AND `target` is not strictly newer.
pub fn is_downgrade_or_prerelease(installed: &str, target: &str) -> bool {
    if is_version_greater(installed, target) {
        return true;
    }
    if has_prerelease_marker(installed) {
        let nums_installed = parse_version_numbers(installed);
        if nums_installed.is_empty() {
            return true;
        }
        return !is_version_greater(target, installed);
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_numbers() {
        assert_eq!(parse_version_numbers("7.4.6"), vec![7, 4, 6]);
        assert_eq!(parse_version_numbers("v7.4.6-beta.1"), vec![7, 4, 6]);
        assert_eq!(parse_version_numbers("oxDesktop 7.5.0"), vec![7, 5, 0]);
        assert_eq!(parse_version_numbers("7.4.6 (dev)"), vec![7, 4, 6]);
    }

    #[test]
    fn test_markers() {
        assert!(has_prerelease_marker("7.5.0-dev"));
        assert!(has_prerelease_marker("7.4.6-beta"));
        assert!(has_prerelease_marker("v7.4.6-preview"));
        assert!(has_prerelease_marker("7.4.6 (dev)"));
        assert!(!has_prerelease_marker("7.4.6"));
        assert!(!has_prerelease_marker("v7.4.6"));
    }

    #[test]
    fn test_is_greater() {
        assert!(is_version_greater("7.5.0", "7.4.6"));
        assert!(is_version_greater("7.4.7", "7.4.6"));
        assert!(is_version_greater("7.4.6.1", "7.4.6"));
        assert!(!is_version_greater("7.4.6", "7.4.6"));
        assert!(!is_version_greater("7.4.4", "7.4.6"));
    }

    #[test]
    fn test_is_downgrade_or_prerelease() {
        // Newer installed version -> downgrade warning
        assert!(is_downgrade_or_prerelease("7.5.0", "7.4.6"));
        assert!(is_downgrade_or_prerelease("7.4.7", "7.4.6"));
        assert!(is_downgrade_or_prerelease("7.5.0-dev", "7.4.6"));

        // Pre-release of same version -> downgrade/warning
        assert!(is_downgrade_or_prerelease("7.4.6-beta", "7.4.6"));
        assert!(is_downgrade_or_prerelease("7.4.6 (dev)", "7.4.6"));

        // Standalone dev/beta string -> downgrade/warning
        assert!(is_downgrade_or_prerelease("dev-build", "7.4.6"));

        // Standard older installed version -> upgrade, no warning
        assert!(!is_downgrade_or_prerelease("7.4.4", "7.4.6"));

        // Same stable version -> no warning
        assert!(!is_downgrade_or_prerelease("7.4.6", "7.4.6"));
        assert!(!is_downgrade_or_prerelease("v7.4.6", "7.4.6"));

        // Older beta upgraded to newer stable -> upgrade, no warning
        assert!(!is_downgrade_or_prerelease("7.4.4-beta", "7.4.6"));
    }
}
