(ns app.ds.modal
  (:require [reagent.core :as r]
            [app.ds.tokens :as t]
            [app.ds.buttons :as btn]))

;; Modal — Pipo design styling: serif title, mono close, subtle border.
;; A11y: role=dialog, aria-modal, aria-labelledby, focus trap, Escape, focus restoration.

(def ^:private focusable-selector
  (str "button:not([disabled]),"
       "[href],"
       "input:not([disabled]),"
       "select:not([disabled]),"
       "textarea:not([disabled]),"
       "[tabindex]:not([tabindex='-1'])"))

(defn- focusables [container]
  (when container
    (.from js/Array (.querySelectorAll container focusable-selector))))

(defn- handle-tab [e container]
  (let [els (focusables container)
        n (alength els)]
    (when (pos? n)
      (let [first-el (aget els 0)
            last-el  (aget els (dec n))
            active   js/document.activeElement]
        (cond
          (and (.-shiftKey e) (= active first-el))
          (do (.preventDefault e) (.focus last-el))

          (and (not (.-shiftKey e)) (= active last-el))
          (do (.preventDefault e) (.focus first-el))

          (not (.contains container active))
          (do (.preventDefault e) (.focus first-el)))))))

(defn- short-id []
  (.substring (str (random-uuid)) 0 8))

(defn- modal-impl []
  (let [container-ref       (atom nil)
        previously-focused  (atom nil)
        keydown-handler-ref (atom nil)
        latest-on-close     (atom nil)
        title-id            (str "ds-modal-title-" (short-id))]
    (r/create-class
     {:component-did-mount
      (fn [this]
        (reset! latest-on-close (-> this r/argv second :on-close))
        (reset! previously-focused js/document.activeElement)
        (let [handler (fn [e]
                        (case (.-key e)
                          "Escape" (when-let [oc @latest-on-close] (oc))
                          "Tab"    (handle-tab e @container-ref)
                          nil))]
          (reset! keydown-handler-ref handler)
          (.addEventListener js/document "keydown" handler))
        ;; Defer initial focus to next tick so the DOM is fully attached.
        (js/setTimeout
         (fn []
           (when-let [els (some-> @container-ref focusables)]
             (when (pos? (alength els))
               (.focus (aget els 0)))))
         0))

      :component-did-update
      (fn [this _]
        (reset! latest-on-close (-> this r/argv second :on-close)))

      :component-will-unmount
      (fn [_]
        (when-let [h @keydown-handler-ref]
          (.removeEventListener js/document "keydown" h))
        (when-let [el @previously-focused]
          (try (.focus el) (catch :default _ nil))))

      :reagent-render
      (fn [{:keys [on-close title size]} & children]
        [:div {:style {:position "fixed" :inset 0 :z-index 1000
                       :display "flex" :align-items "center" :justify-content "center"
                       :padding "16px"}}
         ;; Overlay — clickable scrim. aria-hidden so AT users don't see the
         ;; backdrop as a focusable element. Escape/click both close the dialog.
         [:div {:style {:position "absolute" :inset 0 :background t/overlay}
                :aria-hidden true
                :on-click on-close}]
         (into
          [:div {:role "dialog"
                 :aria-modal "true"
                 :aria-labelledby title-id
                 :ref (fn [el] (reset! container-ref el))
                 :style {:position "relative"
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
            [:h3 {:id title-id
                  :style {:font-family t/font-display :font-size "22px" :font-weight "600"
                          :color t/text-primary :margin 0 :letter-spacing "-0.005em"}}
             title]
            [:button {:on-click on-close
                      :type "button"
                      :aria-label "Fechar"
                      :style {:background t/bg-main :border (str "1px solid " t/border-default)
                              :cursor "pointer"
                              :width "32px" :height "32px" :border-radius (:full t/border-radius)
                              :display "flex" :align-items "center" :justify-content "center"
                              :color t/text-secondary :font-family t/font-mono :font-size "14px"
                              :transition (str "all " t/transition-fast)}}
             [:span {:aria-hidden true} "✕"]]]
           (into [:div {:style {:padding "22px 26px 26px"}}] children)])])})))

(defn modal
  "Modal dialog. Props: open?, on-close, title, size (:sm :md :lg).
   Mounts modal-impl on open, unmounts on close — focus restoration ties to
   that lifecycle."
  [props & children]
  (when (:open? props)
    (into [modal-impl props] children)))

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
