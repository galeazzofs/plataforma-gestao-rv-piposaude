(ns app.ds.tokens-test
  (:require [cljs.test :refer-macros [deftest is testing]]
            [app.ds.tokens :as t]))

(deftest spacing-system-test
  (testing "spacing scale is built on the 8px grid (with 4px half-step)"
    (is (= "0"    (t/sp :0)))
    (is (= "4px"  (t/sp :1)))
    (is (= "8px"  (t/sp :2)))
    (is (= "16px" (t/sp :3)))
    (is (= "24px" (t/sp :4))))

  (testing "unknown keys fall back to '0' rather than nil"
    (is (= "0" (t/sp :nonexistent)))))

(deftest color-definitions-test
  (testing "primary brand colors match the design bundle"
    (is (= "#000000" t/color-primary))
    (is (= "#FFFFFF" t/color-white))
    (is (= "#F6F6F6" t/bg-main))
    (is (= "#000000" t/text-primary)))

  (testing "feedback tokens stay AA-compliant when used as text on -light"
    ;; success-dark, warning-dark, error-dark are the AA-compliant text
    ;; variants used by .badge-* and .delta-* on their `-light` (lightest)
    ;; backgrounds. If any of these are softened the harden pass regresses.
    (is (= "#0F7C50" t/success-dark))
    (is (= "#7A5410" t/warning-dark))
    (is (= "#B91C1C" t/error-dark))))

(deftest typography-test
  (testing "font weight scale is exposed via the weights map"
    (is (= "400" (get t/font-weights :regular)))
    (is (= "500" (get t/font-weights :medium)))
    (is (= "600" (get t/font-weights :semibold)))
    (is (= "700" (get t/font-weights :bold))))

  (testing "font size scale is exposed via the sizes map"
    (is (= "12px" (get t/font-sizes :xs)))
    (is (= "14px" (get t/font-sizes :sm)))
    (is (= "16px" (get t/font-sizes :base)))
    (is (= "24px" (get t/font-sizes :2xl))))

  (testing "font families are wired to design system roles"
    ;; Pipo brand: STIX Two Text for titles (font-display), Manrope for everything else.
    (is (re-find #"Manrope"        t/font-body))
    (is (re-find #"Manrope"        t/font-heading))
    (is (re-find #"Manrope"        t/font-ui))
    (is (re-find #"STIX Two Text"  t/font-display))
    (is (re-find #"Manrope"        t/font-mono))))

(deftest layout-test
  (testing "responsive breakpoints align with the CSS media queries"
    (is (= "576px"  (get t/breakpoints :sm)))
    (is (= "768px"  (get t/breakpoints :md)))
    (is (= "960px"  (get t/breakpoints :lg)))
    (is (= "1140px" (get t/breakpoints :xl))))

  (testing "border radius and pill values match the design"
    (is (= "8px"    (get t/border-radius :sm)))
    (is (= "16px"   (get t/border-radius :lg)))
    (is (= "9999px" (get t/border-radius :full))))

  (testing "padding presets cover xs/sm/md/lg/card"
    (is (= "4px"  (get t/padding :xs)))
    (is (= "8px"  (get t/padding :sm)))
    (is (= "16px" (get t/padding :md)))
    (is (= "24px" (get t/padding :lg)))
    (is (= "24px" (get t/padding :card)))))

(deftest chart-palette-test
  (testing "chart palette is non-empty and starts with a brand-distinct hue"
    (is (sequential? t/chart-colors))
    (is (>= (count t/chart-colors) 4))
    ;; First slot is reserved for the primary series; protects against an
    ;; accidental shuffle that would change every chart's leading color.
    (is (= t/blue-500 (first t/chart-colors)))))
