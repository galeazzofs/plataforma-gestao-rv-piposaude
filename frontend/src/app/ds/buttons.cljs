(ns app.ds.buttons
  (:require [app.ds.tokens :as t]))

(defn button
  "Button component.
   variant: :primary :secondary :ghost :danger
   size: :sm :md :lg
   Props: on-click, disabled, loading, full-width"
  [{:keys [variant size on-click disabled loading full-width class]} & children]
  (let [v (or variant :primary)
        s (or size :md)
        base-style {:font-family t/font-family
                    :font-weight (:semibold t/font-weights)
                    :border-radius (:md t/border-radius)
                    :cursor (if disabled "not-allowed" "pointer")
                    :transition t/transition-fast
                    :display "inline-flex"
                    :align-items "center"
                    :justify-content "center"
                    :gap "8px"
                    :border "none"
                    :width (when full-width "100%")
                    :opacity (if disabled "0.5" "1")}
        size-styles {:sm {:font-size (:xs t/font-sizes) :padding "6px 12px" :height "32px"}
                     :md {:font-size (:sm t/font-sizes) :padding "8px 16px" :height "40px"}
                     :lg {:font-size (:base t/font-sizes) :padding "12px 24px" :height "48px"}}
        variant-styles {:primary   {:background t/color-primary :color t/color-white}
                        :secondary {:background t/bg-surface :color t/text-primary :border (str "1px solid " t/border-default)}
                        :ghost     {:background "transparent" :color t/text-primary}
                        :danger    {:background t/error-default :color t/color-white}}
        merged (merge base-style (get size-styles s) (get variant-styles v))]
    (into [:button {:style merged
                    :on-click (when-not (or disabled loading) on-click)
                    :disabled disabled
                    :class class}]
          (if loading
            [[:span "Carregando..."]]
            children))))
