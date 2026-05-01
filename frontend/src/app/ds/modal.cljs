(ns app.ds.modal
  (:require [app.ds.tokens :as t]
            [app.ds.buttons :as btn]))

;; Modal — Pipo design styling: serif title, mono close, subtle border.

(defn modal
  "Modal dialog. Props: open?, on-close, title, size (:sm :md :lg)"
  [{:keys [open? on-close title size]} & children]
  (when open?
    [:div {:style {:position "fixed" :inset 0 :z-index 1000
                   :display "flex" :align-items "center" :justify-content "center"
                   :padding "16px"}}
     [:div {:style {:position "absolute" :inset 0 :background t/overlay
                    :backdrop-filter "blur(2px)"}
            :on-click on-close}]
     [:div {:style {:position "relative"
                    :background t/bg-card
                    :border (str "1px solid " t/border-default)
                    :border-radius (:lg t/border-radius)
                    :box-shadow (:lg t/shadows)
                    :width (case (or size :md)
                             :sm "440px" :md "560px" :lg "720px" "560px")
                    :max-width "100%"
                    :max-height "90vh"
                    :overflow-y "auto"
                    :display "flex" :flex-direction "column"}}
      [:div {:style {:display "flex" :justify-content "space-between" :align-items "flex-start"
                     :padding "22px 26px 18px"
                     :border-bottom (str "1px solid " t/border-default)
                     :flex-shrink 0}}
       [:h3 {:style {:font-family t/font-display :font-size "22px" :font-weight "400"
                     :color t/text-primary :margin 0 :letter-spacing "-0.005em"}}
        title]
       [:button {:on-click on-close
                 :style {:background t/bg-main :border (str "1px solid " t/border-default)
                         :cursor "pointer"
                         :width "32px" :height "32px" :border-radius (:full t/border-radius)
                         :display "flex" :align-items "center" :justify-content "center"
                         :color t/text-secondary :font-family t/font-mono :font-size "14px"
                         :transition (str "all " t/transition-fast)}}
        "✕"]]
      (into [:div {:style {:padding "22px 26px 26px"}}] children)]]))

(defn confirm-dialog
  "Confirmation dialog. Props: open?, on-close, on-confirm, title, message,
   confirm-label, variant"
  [{:keys [open? on-close on-confirm title message confirm-label variant]}]
  [modal {:open? open? :on-close on-close :title title :size :sm}
   [:p {:style {:color t/text-tertiary :margin "0 0 24px" :font-size "13px" :line-height "1.6"}}
    message]
   [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"}}
    [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
    [btn/button {:variant (or variant :primary) :on-click on-confirm}
     (or confirm-label "Confirmar")]]])
