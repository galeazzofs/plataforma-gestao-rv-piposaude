(ns app.ds.buttons
  (:require [app.ds.tokens :as t]))

(defn button
  "Button component, styled to match the Pipo design.
   variant: :primary :secondary :ghost :danger
   size: :sm :md :lg
   Props: on-click, disabled, loading, full-width"
  [{:keys [variant size on-click disabled loading full-width class type]} & children]
  (let [v (or variant :primary)
        s (or size :md)
        base-style {:font-family t/font-ui
                    :font-weight (:semibold t/font-weights)
                    :border-radius (:sm t/border-radius)
                    :cursor (if (or disabled loading) "not-allowed" "pointer")
                    :transition (str "all " t/transition-fast)
                    :display "inline-flex"
                    :align-items "center"
                    :justify-content "center"
                    :gap "8px"
                    :line-height "1"
                    :border "1px solid transparent"
                    :width (when full-width "100%")
                    :opacity (if (or disabled loading) "0.5" "1")
                    :white-space "nowrap"
                    :letter-spacing "0"}
        size-styles {:sm {:font-size "11px" :padding "6px 11px" :min-height "28px"}
                     :md {:font-size "13px" :padding "9px 16px" :min-height "36px"}
                     :lg {:font-size "14px" :padding "12px 22px" :min-height "44px"}}
        variant-styles {:primary   {:background t/color-primary :color t/color-white}
                        :secondary {:background t/bg-card :color t/text-primary
                                    :border (str "1px solid " t/border-default)}
                        :ghost     {:background "transparent" :color t/text-secondary}
                        :danger    {:background t/error-light :color t/error-dark
                                    :border (str "1px solid " t/error-light)}}
        merged (merge base-style (get size-styles s) (get variant-styles v))]
    (into [:button {:style merged
                    :type (or type "button")
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
