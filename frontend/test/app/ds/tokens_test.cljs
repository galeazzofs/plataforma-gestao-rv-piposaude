(ns app.ds.tokens-test
  (:require [cljs.test :refer-macros [deftest is testing]]
            [app.ds.tokens :as tokens]))

(deftest spacing-system-test
  (testing "spacing scale is built on the 8px grid (with 4px half-step)"
    (is (= "0"    (tokens/sp :0)))
    (is (= "4px"  (tokens/sp :1)))
    (is (= "8px"  (tokens/sp :2)))
    (is (= "16px" (tokens/sp :3)))
    (is (= "24px" (tokens/sp :4))))

  (testing "unknown keys fall back to '0' rather than nil"
    (is (= "0" (tokens/sp :nonexistent)))))

(deftest color-definitions-test
  (testing "primary brand colors match the design bundle"
    (is (= "#000000" tokens/color-primary))
    (is (= "#FFFFFF" tokens/color-white))
    (is (= "#F6F6F6" tokens/bg-main))
    (is (= "#000000" tokens/text-primary)))

  (testing "feedback tokens stay AA-compliant when used as text on -light"
    ;; success-dark, warning-dark, error-dark are the AA-compliant text
    ;; variants used by .badge-* and .delta-* on their `-light` (lightest)
    ;; backgrounds. If any of these are softened the harden pass regresses.
    (is (= "#0F7C50" tokens/success-dark))
    (is (= "#7A5410" tokens/warning-dark))
    (is (= "#B91C1C" tokens/error-dark))))

(deftest typography-test
  (testing "font weight scale is exposed via the weights map"
    (is (= "400" (get tokens/font-weights :regular)))
    (is (= "500" (get tokens/font-weights :medium)))
    (is (= "600" (get tokens/font-weights :semibold)))
    (is (= "700" (get tokens/font-weights :bold))))

  (testing "font size scale is exposed via the sizes map"
    (is (= "12px" (get tokens/font-sizes :xs)))
    (is (= "14px" (get tokens/font-sizes :sm)))
    (is (= "16px" (get tokens/font-sizes :base)))
    (is (= "24px" (get tokens/font-sizes :2xl))))

  (testing "font families are wired to design system roles"
    (is (re-find #"Work Sans"        tokens/font-body))
    (is (re-find #"Poppins"          tokens/font-heading))
    (is (re-find #"Manrope"          tokens/font-ui))
    (is (re-find #"DM Serif Display" tokens/font-display))
    (is (re-find #"IBM Plex Mono"    tokens/font-mono))))

(deftest layout-test
  (testing "responsive breakpoints align with the CSS media queries"
    (is (= "576px"  (get tokens/breakpoints :sm)))
    (is (= "768px"  (get tokens/breakpoints :md)))
    (is (= "960px"  (get tokens/breakpoints :lg)))
    (is (= "1140px" (get tokens/breakpoints :xl))))

  (testing "border radius and pill values match the design"
    (is (= "8px"    (get tokens/border-radius :sm)))
    (is (= "16px"   (get tokens/border-radius :lg)))
    (is (= "9999px" (get tokens/border-radius :full))))

  (testing "padding presets cover xs/sm/md/lg/card"
    (is (= "4px"  (get tokens/padding :xs)))
    (is (= "8px"  (get tokens/padding :sm)))
    (is (= "16px" (get tokens/padding :md)))
    (is (= "24px" (get tokens/padding :lg)))
    (is (= "24px" (get tokens/padding :card)))))

(deftest chart-palette-test
  (testing "chart palette is non-empty and starts with a brand-distinct hue"
    (is (sequential? tokens/chart-colors))
    (is (>= (count tokens/chart-colors) 4))
    ;; First slot is reserved for the primary series; protects against an
    ;; accidental shuffle that would change every chart's leading color.
    (is (= tokens/blue-500 (first tokens/chart-colors)))))
