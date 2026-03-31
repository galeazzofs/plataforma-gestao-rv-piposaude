(ns app.ds.modal
  (:require [app.ds.tokens :as t]
            [app.ds.buttons :as btn]))

(defn modal
  "Modal dialog.
   Props: open?, on-close, title, size (:sm :md :lg)"
  [{:keys [open? on-close title size]} & children]
  (when open?
    [:div {:style {:position "fixed" :inset "0" :z-index "1000"
                   :display "flex" :align-items "center" :justify-content "center"
                   :padding "16px"}}
     ;; Overlay
     [:div {:style {:position "absolute" :inset "0" :background t/overlay}
            :on-click on-close}]
     ;; Content
     [:div {:style {:position "relative"
                    :background t/bg-card
                    :border-radius (:xl t/border-radius)
                    :box-shadow (:lg t/shadows)
                    :width (case (or size :md)
                             :sm "420px"
                             :md "560px"
                             :lg "720px"
                             "560px")
                    :max-width "100%"
                    :max-height "90vh"
                    :overflow-y "auto"
                    :display "flex"
                    :flex-direction "column"}}
      ;; Header
      [:div {:style {:display "flex" :justify-content "space-between" :align-items "center"
                     :padding "24px 28px 20px"
                     :border-bottom (str "1px solid " t/border-default)
                     :flex-shrink "0"}}
       [:h3 {:style {:font-size (:xl t/font-sizes) :font-weight (:semibold t/font-weights)
                     :margin "0" :color t/text-primary}} title]
       [:button {:style {:background t/bg-main :border "none" :cursor "pointer"
                         :width "32px" :height "32px" :border-radius (:md t/border-radius)
                         :display "flex" :align-items "center" :justify-content "center"
                         :color t/text-secondary :font-size "18px"
                         :transition (str "all " t/transition-fast)}
                 :on-click on-close} "✕"]]
      ;; Body
      (into [:div {:style {:padding "24px 28px"}}] children)]]))

(defn confirm-dialog
  "Confirmation dialog.
   Props: open?, on-close, on-confirm, title, message, confirm-label, variant"
  [{:keys [open? on-close on-confirm title message confirm-label variant]}]
  [modal {:open? open? :on-close on-close :title title :size :sm}
   [:p {:style {:color t/text-secondary :margin-bottom "24px" :margin-top "0"
                :font-size (:sm t/font-sizes) :line-height "1.6"}} message]
   [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"}}
    [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
    [btn/button {:variant (or variant :primary) :on-click on-confirm}
     (or confirm-label "Confirmar")]]])
