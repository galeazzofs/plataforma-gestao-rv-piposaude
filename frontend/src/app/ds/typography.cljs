(ns app.ds.typography
  (:require [app.ds.tokens :as t]))

(defn heading
  "Heading component. level: 1-4, children: content."
  [{:keys [level class]} & children]
  (let [tag (keyword (str "h" (or level 1)))
        styles {:h1 {:font-size (:4xl t/font-sizes) :font-weight (:bold t/font-weights) :line-height (:tight t/line-heights) :color t/text-primary :margin "0"}
                :h2 {:font-size (:3xl t/font-sizes) :font-weight (:bold t/font-weights) :line-height (:tight t/line-heights) :color t/text-primary :margin "0"}
                :h3 {:font-size (:2xl t/font-sizes) :font-weight (:semibold t/font-weights) :line-height (:tight t/line-heights) :color t/text-primary :margin "0"}
                :h4 {:font-size (:xl t/font-sizes) :font-weight (:semibold t/font-weights) :line-height (:tight t/line-heights) :color t/text-primary :margin "0"}}]
    (into [tag {:style (get styles tag (:h1 styles))
                :class class}]
          children)))

(defn text
  "Body text. size: :xs :sm :base :lg, variant: :primary :secondary :disabled."
  [{:keys [size variant class style]} & children]
  (let [color (case (or variant :primary)
                :primary   t/text-primary
                :secondary t/text-secondary
                :disabled  t/text-disabled
                t/text-primary)
        font-size (get t/font-sizes (or size :base) (:base t/font-sizes))]
    (into [:p {:style (merge {:font-size font-size
                              :color color
                              :line-height (:normal t/line-heights)
                              :margin "0"
                              :font-family t/font-family}
                             style)
               :class class}]
          children)))

(defn label
  "Form label."
  [{:keys [required class]} & children]
  (into [:label {:style {:font-size (:sm t/font-sizes)
                         :font-weight (:medium t/font-weights)
                         :color t/text-primary
                         :margin-bottom "4px"
                         :display "block"}
                 :class class}]
        (concat children
                (when required
                  [[:span {:style {:color t/error-default :margin-left "4px"}} "*"]]))))
