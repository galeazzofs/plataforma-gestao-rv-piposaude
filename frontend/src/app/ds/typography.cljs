(ns app.ds.typography
  (:require [app.ds.tokens :as t]))

;; The Pipo design uses DM Serif Display for hero/H1 titles, Poppins for
;; structural headings, and Manrope/Work Sans for UI labels. Sizes here mirror
;; the .h* spec from shared.css.

(defn heading
  "Heading component. level: 1-4."
  [{:keys [level class display?]} & children]
  (let [tag (keyword (str "h" (or level 1)))
        font (if display? t/font-display t/font-heading)
        styles {:h1 {:font-family font :font-size "28px" :line-height "1.15"
                     :font-weight (if display? "400" (:semibold t/font-weights))
                     :color t/text-primary :margin "0" :letter-spacing "-0.005em"}
                :h2 {:font-family font :font-size "22px" :line-height "1.2"
                     :font-weight (if display? "400" (:semibold t/font-weights))
                     :color t/text-primary :margin "0" :letter-spacing "-0.005em"}
                :h3 {:font-family t/font-heading :font-size "16px" :line-height "1.3"
                     :font-weight (:semibold t/font-weights)
                     :color t/text-primary :margin "0" :letter-spacing "-0.005em"}
                :h4 {:font-family t/font-heading :font-size "14px" :line-height "1.4"
                     :font-weight (:semibold t/font-weights)
                     :color t/text-primary :margin "0"}}]
    (into [tag {:style (get styles tag (:h1 styles))
                :class class}]
          children)))

(defn text
  "Body text. size: :xs :sm :base :lg, variant: :primary :secondary :disabled."
  [{:keys [size variant class style]} & children]
  (let [color (case (or variant :primary)
                :primary   t/text-primary
                :secondary t/text-secondary
                :tertiary  t/text-tertiary
                :disabled  t/text-disabled
                t/text-primary)
        font-size (get t/font-sizes (or size :base) (:base t/font-sizes))]
    (into [:p {:style (merge {:font-size font-size
                              :color color
                              :line-height (:normal t/line-heights)
                              :margin "0"
                              :font-family t/font-body}
                             style)
               :class class}]
          children)))

(defn label
  "Form label. Pass :for to associate with an input id (preferred for a11y)."
  [{:keys [required class for]} & children]
  (let [base-attrs {:style {:font-family t/font-ui
                            :font-size "12px"
                            :font-weight (:semibold t/font-weights)
                            :color t/text-secondary
                            :margin-bottom "4px"
                            :display "block"}
                    :class class}
        attrs (cond-> base-attrs
                for (assoc :html-for for))]
    (into [:label attrs]
          (concat children
                  (when required
                    [[:span {:style {:color t/error-default :margin-left "4px"}
                             :aria-hidden true}
                      "*"]
                     [:span {:style {:position "absolute"
                                     :width "1px" :height "1px"
                                     :padding 0 :margin "-1px"
                                     :overflow "hidden" :clip "rect(0,0,0,0)"
                                     :white-space "nowrap" :border 0}}
                      " (obrigatório)"]])))))
