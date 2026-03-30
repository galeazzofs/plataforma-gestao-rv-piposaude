(ns app.ds.tokens-test
  (:require [cljs.test :refer-macros [deftest is testing]]
            [app.ds.tokens :as tokens]))

(deftest spacing-system-test
  (testing "spacing values are multiples of 4px"
    (is (= "8px" (tokens/sp :2)))
    (is (= "16px" (tokens/sp :3)))
    (is (= "0" (tokens/sp :0)))))

(deftest color-definitions-test
  (testing "primary colors are defined"
    (is (= "#000000" tokens/color-primary))
    (is (= "#F7F6F3" tokens/bg-main))
    (is (= "#2B2B2B" tokens/text-primary))))
