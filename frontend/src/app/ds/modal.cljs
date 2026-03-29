(ns app.ds.modal
  (:require [app.ds.tokens :as t]
            [app.ds.buttons :as btn]))

(defn modal
  "Modal dialog.
   Props: open?, on-close, title, size (:sm :md :lg)"
  [{:keys [open? on-close title size]} & children]
  (when open?
    [:div {:style {:position "fixed" :inset "0" :z-index "1000"
                   :display "flex" :align-items "center" :justify-content "center"}}
     ;; Overlay
     [:div {:style {:position "absolute" :inset "0" :background t/overlay}
            :on-click on-close}]
     ;; Content
     [:div {:style {:position "relative"
                    :background t/bg-card
                    :border-radius (:xl t/border-radius)
                    :box-shadow (:lg t/shadows)
                    :padding "32px"
                    :width (case (or size :md)
                             :sm "400px"
                             :md "560px"
                             :lg "720px"
                             "560px")
                    :max-height "90vh"
                    :overflow-y "auto"}}
      ;; Header
      [:div {:style {:display "flex" :justify-content "space-between" :align-items "center" :margin-bottom "24px"}}
       [:h3 {:style {:font-size (:xl t/font-sizes) :font-weight (:semibold t/font-weights) :margin "0"}} title]
       [:button {:style {:background "none" :border "none" :cursor "pointer"
                         :font-size "20px" :color t/text-secondary :padding "4px"}
                 :on-click on-close} "✕"]]
      ;; Body
      (into [:div] children)]]))

(defn confirm-dialog
  "Confirmation dialog.
   Props: open?, on-close, on-confirm, title, message, confirm-label, variant"
  [{:keys [open? on-close on-confirm title message confirm-label variant]}]
  [modal {:open? open? :on-close on-close :title title :size :sm}
   [:p {:style {:color t/text-secondary :margin-bottom "24px"}} message]
   [:div {:style {:display "flex" :gap "12px" :justify-content "flex-end"}}
    [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
    [btn/button {:variant (or variant :primary) :on-click on-confirm}
     (or confirm-label "Confirmar")]]])
