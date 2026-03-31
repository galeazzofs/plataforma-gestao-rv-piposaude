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
                    :cursor (if (or disabled loading) "not-allowed" "pointer")
                    :transition (str "all " t/transition-fast)
                    :display "inline-flex"
                    :align-items "center"
                    :justify-content "center"
                    :gap "6px"
                    :border "none"
                    :width (when full-width "100%")
                    :opacity (if (or disabled loading) "0.5" "1")
                    :white-space "nowrap"
                    :letter-spacing "0.01em"}
        size-styles {:sm {:font-size (:xs t/font-sizes) :padding "0 10px" :height "32px" :min-width "64px"}
                     :md {:font-size (:sm t/font-sizes) :padding "0 16px" :height "40px" :min-width "80px"}
                     :lg {:font-size (:base t/font-sizes) :padding "0 24px" :height "48px" :min-width "100px"}}
        variant-styles {:primary   {:background t/color-primary :color t/color-white
                                    :box-shadow "0 1px 2px rgba(0,0,0,0.1)"}
                        :secondary {:background t/bg-card :color t/text-primary
                                    :border (str "1px solid " t/border-default)
                                    :box-shadow (:sm t/shadows)}
                        :ghost     {:background "transparent" :color t/text-secondary
                                    :padding "0 8px"}
                        :danger    {:background t/error-default :color t/color-white
                                    :box-shadow "0 1px 2px rgba(239,68,68,0.2)"}}
        merged (merge base-style (get size-styles s) (get variant-styles v))]
    (into [:button {:style merged
                    :on-click (when-not (or disabled loading) on-click)
                    :disabled (or disabled loading)
                    :class class}]
          (if loading
            [[:span {:style {:display "inline-flex" :align-items "center" :gap "6px"}}
              [:span {:style {:width "14px" :height "14px" :border "2px solid currentColor"
                              :border-top-color "transparent" :border-radius "50%"
                              :animation "spin 0.6s linear infinite"}} ""]
              "Carregando..."]]
            children))))
